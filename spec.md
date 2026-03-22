# ollama-top — Project Specification

## Overview

A `top`-like terminal UI (TUI) for monitoring a locally running Ollama instance in real time.
Zero configuration, no proxy, no sudo — just run it and it works.

## Design Constraints

- **Zero config**: auto-detect Ollama via `$OLLAMA_HOST`, fallback to `localhost:11434`
- **No proxy**: do not intercept or reroute Ollama traffic
- **No sudo**: must work as a limited (non-admin) user
- **No API keys**: Ollama's local API is unauthenticated
- **Cross-platform**: macOS and Linux, bare Python (in venv) or Docker
- **Installable via `pipx`**: single command to install and run
- **Python 3.13**: requires Python >= 3.13

## Why These Constraints

This was developed for a macOS Mac Mini where:
- Ollama runs as a Launch Agent (menu bar app, installed via curl)
- The user is a limited (non-admin) account
- `log stream`, `powermetrics`, BPF sockets all require admin/sudo — ruled out
- GPU metrics are therefore not available and should be omitted entirely rather than shown incorrectly

## Data Sources

Everything comes from Ollama's local HTTP API. No system-level introspection.

| Metric | Source |
|---|---|
| Loaded models, VRAM usage, expiry | `GET /api/ps` polled every 1s |
| Ollama version | `GET /api/version` at startup |
| CPU % | `psutil.cpu_percent()` |
| RAM used / total | `psutil.virtual_memory()` |
| Tokens/sec | Derived: watch `/api/ps` for active inference, time deltas |
| Request history | SQLite ring buffer written by collector |

**No GPU metrics.** Do not show a GPU panel. Accept this limitation cleanly.

## Token/s Estimation

Ollama's `/api/ps` response includes a `status` field per model:
- `"idle"` — model loaded, not inferring
- `"running"` — actively generating tokens

By timing transitions from `idle` → `running` → `idle` and tracking `expires_at` resets,
we can estimate rough throughput. This is coarse but honest — label it as estimated.

The completed response JSON (from `/api/generate` or `/api/chat`) includes:
- `eval_count` — tokens generated
- `eval_duration` — nanoseconds spent generating
- `prompt_eval_count` — prompt tokens
- `prompt_eval_duration` — nanoseconds spent on prompt

Since we're not proxying, we only see these if we make requests ourselves.
The collector should NOT make inference requests — only observe via `/api/ps`.

## UI — Textual TUI

Use the [Textual](https://textual.textualize.io/) framework.

### Layout

```
┌─ ollama-top ─────────────────── localhost:11434 ── v0.3.x ── q to quit ─┐
│                                                                           │
├─ Loaded Models ───────────────────────────────────────────────────────────┤
│ MODEL                  SIZE      VRAM      STATUS    EXPIRES              │
│ qwen2.5:14b            8.9 GB    8.9 GB    running   2m 14s               │
│ deepseek-r1:8b         4.7 GB    4.7 GB    idle      8m 02s               │
│                                                                           │
├─ Performance ─────────────────────────────────────────────────────────────┤
│ tokens/sec (est)   ▁▂▄▆█▇▅▃▂▄▆█   ~42 tok/s                              │
│ active requests    1                                                      │
│                                                                           │
├─ System ──────────────────────────────────────────────────────────────────┤
│ CPU   ████████░░  78%          RAM   12.4 GB / 32.0 GB  (38%)            │
└───────────────────────────────────────────────────────────────────────────┘
```

### Textual guidelines
- Use `textual` >= 0.61
- Use `DataTable` for the models panel
- Use `Sparkline` widget (built into Textual) for tok/s history
- Use `ProgressBar` for CPU and RAM
- Refresh interval: 1 second via `set_interval`
- Handle connection errors gracefully: show "Cannot connect to Ollama at <host>" and retry
- `q` or `Ctrl+C` to quit

## File Structure

```
ollama-top/
├── SPEC.md                  # this file
├── README.md
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── ollama_top/
    ├── __init__.py
    ├── __main__.py          # entry point: parses args, launches TUI
    ├── config.py            # resolve Ollama host URL, constants
    ├── collector.py         # async polling loop, writes to DB
    ├── db.py                # SQLite schema, ring buffer queries
    └── tui.py               # Textual app, all widgets and layout
```

## config.py

- Read `$OLLAMA_HOST`, normalize to include `http://` scheme
- Fallback: `http://localhost:11434`
- Constants: `POLL_INTERVAL = 1.0`, `SPARKLINE_WIDTH = 20`, `DB_PATH = ~/.local/share/ollama-top/history.db`

## collector.py

- `OllamaCollector` — async class, runs in background
- Methods:
  - `get_version()` → str
  - `get_models()` → list of model dicts from `/api/ps`
  - `get_system()` → dict with cpu_pct, ram_used, ram_total
  - `poll_loop()` → infinite loop, writes snapshots to DB, fires callbacks
- Detect model status changes (idle → running) to estimate inference start time
- On connection error: set `connected = False`, surface to TUI, keep retrying

## db.py

- SQLite at `DB_PATH` (create dirs if needed)
- Two tables:
  - `snapshots` — timestamp, model_name, status, vram_bytes
  - `throughput` — timestamp, tokens_per_sec (estimated)
- Ring buffer: keep last 1000 rows per table, delete older on insert
- Query: `get_recent_throughput(n=20)` → list of floats for sparkline

## __main__.py

```python
def main():
    # parse --host flag (overrides $OLLAMA_HOST)
    # initialize DB
    # launch Textual app
```

## pyproject.toml

```toml
[project]
name = "ollama-top"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "textual>=0.61.0",
    "aiohttp>=3.9.0",
    "psutil>=5.9.0",
]

[project.scripts]
ollama-top = "ollama_top.__main__:main"
```

## Installation (target UX)

### Via pipx
```bash
pipx install ollama-top
ollama-top
```

### Development (bare Python in venv)
```bash
git clone https://github.com/evandhoffman/ollama-top
cd ollama-top
uv sync
uv run ollama-top
```

### Docker
```bash
docker build -t ollama-top .
docker run --rm -it --network host ollama-top
```

Note: `--network host` is needed so the container can reach Ollama on localhost.
Alternatively, pass `--host` to point at the Docker host IP.

## Dockerfile

- Base image: `cgr.dev/chainguard/python:latest-dev` (Wolfi-based, low CVE surface)
- Multi-stage build: install deps with uv in a builder stage, copy `.venv` to runtime
- Copy uv binary from `ghcr.io/astral-sh/uv:latest` rather than installing it
- Runtime user: `nonroot`
- Create writable `/data` dir for SQLite DB before `USER nonroot`
- Set `OLLAMA_HOST` default to `http://host.docker.internal:11434` for convenience
- Entry point: `ollama-top`

## Out of Scope

- GPU metrics (requires sudo on macOS)
- Proxy/interception mode
- Multi-host monitoring
- Authentication / TLS (Ollama local API has none)
- Windows support

## Known Limitations

- Token/s is estimated from polling, not measured directly — label it clearly in the UI
- If Ollama is not running, show a clear error and retry rather than crashing
- VRAM numbers come from Ollama's own reporting, which reflects model weights only

