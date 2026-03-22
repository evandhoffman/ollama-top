"""Async polling loop for Ollama API and system metrics."""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

import aiohttp
import psutil

from ollama_top.config import POLL_INTERVAL

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Snapshot of a single loaded model from /api/ps."""

    name: str
    size: int  # bytes
    vram_size: int  # bytes
    status: str  # "running" or "idle"
    expires_at: datetime | None = None


@dataclass
class SystemInfo:
    """CPU and RAM snapshot."""

    cpu_pct: float
    ram_used: int  # bytes
    ram_total: int  # bytes


@dataclass
class Snapshot:
    """Complete data from one poll cycle."""

    connected: bool = True
    version: str = ""
    models: list[ModelInfo] = field(default_factory=list)
    system: SystemInfo = field(default_factory=lambda: SystemInfo(0.0, 0, 0))
    active_count: int = 0
    estimated_tps: float = 0.0


# Type for the callback the TUI registers
SnapshotCallback = Callable[[Snapshot], None]


class OllamaCollector:
    """Polls Ollama's API and system metrics, fires callbacks with snapshots."""

    def __init__(self, host: str) -> None:
        self.host = host
        self.connected = False
        self.version = ""
        self._session: aiohttp.ClientSession | None = None
        self._callbacks: list[SnapshotCallback] = []
        # Track expires_at per model to detect activity
        self._prev_expires: dict[str, str] = {}
        # Track inference timing for tok/s estimation
        self._inference_start: dict[str, float] = {}

    def on_snapshot(self, cb: SnapshotCallback) -> None:
        """Register a callback to receive each poll snapshot."""
        self._callbacks.append(cb)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def get_version(self) -> str:
        """Fetch Ollama version string."""
        session = await self._ensure_session()
        async with session.get(f"{self.host}/api/version") as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("version", "unknown")

    async def get_models(self) -> list[ModelInfo]:
        """Fetch loaded models from /api/ps."""
        session = await self._ensure_session()
        async with session.get(f"{self.host}/api/ps") as resp:
            resp.raise_for_status()
            data = await resp.json()

        models: list[ModelInfo] = []
        for m in data.get("models", []):
            expires_at = None
            expires_raw = m.get("expires_at", "")
            if expires_raw:
                try:
                    expires_at = datetime.fromisoformat(expires_raw)
                except (ValueError, TypeError):
                    pass

            size = m.get("size", 0)
            vram_size = m.get("size_vram", 0)

            # Detect activity: if expires_at changed since last poll, the model
            # is actively being used (Ollama resets the timer on each request).
            prev_exp = self._prev_expires.get(m.get("name", ""))
            if prev_exp is not None and expires_raw and expires_raw != prev_exp:
                status = "running"
            else:
                status = "idle"

            models.append(
                ModelInfo(
                    name=m.get("name", "unknown"),
                    size=size,
                    vram_size=vram_size,
                    status=status,
                    expires_at=expires_at,
                )
            )

        # Update tracking state
        self._prev_expires = {
            m.get("name", ""): m.get("expires_at", "")
            for m in data.get("models", [])
        }

        return models

    def get_system(self) -> SystemInfo:
        """Get CPU and RAM usage via psutil."""
        vm = psutil.virtual_memory()
        return SystemInfo(
            cpu_pct=psutil.cpu_percent(interval=None),
            ram_used=vm.used,
            ram_total=vm.total,
        )

    def _detect_activity(self, models: list[ModelInfo]) -> tuple[int, float]:
        """Count active models and estimate throughput.

        Returns (active_count, estimated_tokens_per_sec).
        """
        now = time.monotonic()
        active = 0
        tps = 0.0

        for m in models:
            if m.status == "running":
                active += 1
                if m.name not in self._inference_start:
                    self._inference_start[m.name] = now
                    logger.debug("Model %s started inference", m.name)
            else:
                # Model is idle — if it was previously running, the inference ended
                start = self._inference_start.pop(m.name, None)
                if start is not None:
                    duration = now - start
                    logger.debug(
                        "Model %s finished inference in %.1fs", m.name, duration
                    )

        return active, tps

    async def poll_loop(self) -> None:
        """Infinite polling loop. Fires callbacks each cycle."""
        # Seed cpu_percent so the first real call returns a meaningful value
        psutil.cpu_percent(interval=None)

        while True:
            snapshot = Snapshot()

            try:
                if not self.connected:
                    self.version = await self.get_version()
                    self.connected = True
                    logger.info(
                        "Connected to Ollama at %s (v%s)", self.host, self.version
                    )

                snapshot.version = self.version
                snapshot.connected = True
                snapshot.models = await self.get_models()
                snapshot.system = self.get_system()
                snapshot.active_count, snapshot.estimated_tps = self._detect_activity(
                    snapshot.models
                )

            except (aiohttp.ClientError, OSError) as exc:
                if self.connected:
                    logger.warning("Lost connection to Ollama: %s", exc)
                self.connected = False
                snapshot.connected = False
                snapshot.system = self.get_system()

            for cb in self._callbacks:
                try:
                    cb(snapshot)
                except Exception:
                    logger.exception("Snapshot callback error")

            await asyncio.sleep(POLL_INTERVAL)

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
