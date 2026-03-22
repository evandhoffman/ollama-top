"""Textual TUI application for ollama-top."""

import logging
from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Label, ProgressBar, Sparkline, Static

from ollama_top.collector import OllamaCollector, Snapshot

logger = logging.getLogger(__name__)


def _human_bytes(n: int | float) -> str:
    """Format bytes as human-readable string (e.g. 8.9 GB)."""
    value = float(n)
    if value < 1024:
        return f"{value:.0f} B"
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} PB"


def _countdown(dt: datetime | None) -> str:
    """Format a future datetime as a countdown string (e.g. 2m 14s)."""
    if dt is None:
        return "—"
    now = datetime.now(timezone.utc)
    # Ensure dt is timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = dt - now
    total_secs = int(delta.total_seconds())
    if total_secs <= 0:
        return "expiring"
    minutes, secs = divmod(total_secs, 60)
    if minutes > 0:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


class OllamaTop(App):
    """Main TUI application."""

    TITLE = "ollama-top"
    CSS = """
    Screen {
        layout: vertical;
    }
    #header-bar {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        text-align: center;
    }
    #error-container {
        align: center middle;
        height: 100%;
    }
    #error-message {
        text-align: center;
        color: $error;
        text-style: bold;
    }
    .panel-title {
        background: $surface;
        color: $text;
        text-style: bold;
        padding: 0 1;
    }
    #models-table {
        height: auto;
        max-height: 12;
    }
    #perf-panel {
        height: auto;
        padding: 0 1;
    }
    #sparkline-row {
        height: 3;
    }
    #tps-label {
        width: auto;
        margin-left: 1;
    }
    #active-label {
        padding: 0 1;
    }
    #sys-panel {
        height: auto;
        padding: 0 1;
    }
    .bar-row {
        height: 1;
        padding: 0 0;
    }
    .bar-label {
        width: 8;
    }
    .bar-pct {
        width: auto;
        min-width: 12;
        text-align: right;
    }
    ProgressBar {
        width: 1fr;
    }
    ProgressBar Bar {
        width: 1fr;
    }
    ProgressBar PercentageStatus {
        display: none;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(self, collector: OllamaCollector) -> None:
        super().__init__()
        self._collector = collector
        self._latest: Snapshot | None = None
        self._activity_history: list[float] = []
        self._collector.on_snapshot(self._on_snapshot)

    def compose(self) -> ComposeResult:
        yield Static(
            f"ollama-top — {self._collector.host} — q to quit",
            id="header-bar",
        )
        with Vertical(id="error-container"):
            yield Label("Connecting to Ollama...", id="error-message")
        with Vertical(id="main-content"):
            yield Static("Loaded Models", classes="panel-title")
            yield DataTable(id="models-table")
            yield Static("Performance", classes="panel-title")
            with Vertical(id="perf-panel"):
                with Horizontal(id="sparkline-row"):
                    yield Sparkline([], id="activity-sparkline")
                    yield Label("0 active", id="activity-label")
                yield Label("models loaded  0", id="models-label")
            yield Static("System", classes="panel-title")
            with Vertical(id="sys-panel"):
                with Horizontal(classes="bar-row"):
                    yield Label("CPU", classes="bar-label")
                    yield ProgressBar(total=100, show_percentage=False, id="cpu-bar")
                    yield Label("  0%", classes="bar-pct", id="cpu-pct")
                with Horizontal(classes="bar-row"):
                    yield Label("RAM", classes="bar-label")
                    yield ProgressBar(total=100, show_percentage=False, id="ram-bar")
                    yield Label("  0%", classes="bar-pct", id="ram-pct")
        yield Footer()

    def on_mount(self) -> None:
        # Set up the models table columns
        table = self.query_one("#models-table", DataTable)
        table.add_columns("MODEL", "SIZE", "VRAM", "STATUS", "EXPIRES")

        # Hide main content until connected
        self.query_one("#main-content").display = False
        self.query_one("#error-container").display = True

        # Start the poll loop as a background task
        self.run_worker(self._run_collector(), exclusive=True)

        # Refresh UI every second
        self.set_interval(1.0, self._refresh_ui)

    async def _run_collector(self) -> None:
        """Run the collector poll loop."""
        try:
            await self._collector.poll_loop()
        except Exception:
            logger.exception("Collector poll loop crashed")

    def _on_snapshot(self, snapshot: Snapshot) -> None:
        """Callback from collector — store latest snapshot."""
        self._latest = snapshot
        # Always record activity count so the sparkline has data
        self._activity_history.append(float(snapshot.active_count))
        self._activity_history = self._activity_history[-20:]

    def _refresh_ui(self) -> None:
        """Update all widgets with latest snapshot data."""
        snap = self._latest
        if snap is None:
            return

        error_container = self.query_one("#error-container")
        main_content = self.query_one("#main-content")

        if not snap.connected:
            error_container.display = True
            main_content.display = False
            self.query_one("#error-message", Label).update(
                f"Cannot connect to Ollama at {self._collector.host}\nRetrying..."
            )
            # Still update system bars even when disconnected
            self._update_system(snap)
            return

        error_container.display = False
        main_content.display = True

        # Update header with version
        self.query_one("#header-bar", Static).update(
            f"ollama-top — {self._collector.host} — v{snap.version} — q to quit"
        )

        self._update_models(snap)
        self._update_perf(snap)
        self._update_system(snap)

    def _update_models(self, snap: Snapshot) -> None:
        """Refresh the models DataTable."""
        table = self.query_one("#models-table", DataTable)
        table.clear()
        for m in snap.models:
            table.add_row(
                m.name,
                _human_bytes(m.size),
                _human_bytes(m.vram_size),
                m.status,
                _countdown(m.expires_at),
            )

    def _update_perf(self, snap: Snapshot) -> None:
        """Refresh the performance panel."""
        sparkline = self.query_one("#activity-sparkline", Sparkline)
        sparkline.data = self._activity_history if self._activity_history else [0.0]

        active = snap.active_count
        label = f"{active} active" if active != 1 else "1 active"
        self.query_one("#activity-label", Label).update(label)
        self.query_one("#models-label", Label).update(
            f"models loaded  {len(snap.models)}"
        )

    def _update_system(self, snap: Snapshot) -> None:
        """Refresh CPU and RAM bars."""
        cpu_bar = self.query_one("#cpu-bar", ProgressBar)
        cpu_bar.update(progress=snap.system.cpu_pct)
        self.query_one("#cpu-pct", Label).update(f"{snap.system.cpu_pct:5.1f}%")

        ram_pct = (
            snap.system.ram_used / snap.system.ram_total * 100
            if snap.system.ram_total > 0
            else 0.0
        )
        ram_bar = self.query_one("#ram-bar", ProgressBar)
        ram_bar.update(progress=ram_pct)
        ram_used_h = _human_bytes(snap.system.ram_used)
        ram_total_h = _human_bytes(snap.system.ram_total)
        self.query_one("#ram-pct", Label).update(
            f"{ram_used_h} / {ram_total_h}  ({ram_pct:.0f}%)"
        )
