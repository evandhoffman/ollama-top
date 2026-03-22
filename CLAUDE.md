# CLAUDE.md

## Project overview

ollama-top is a terminal UI (TUI) for monitoring a local Ollama instance. Built with Textual, it polls Ollama's HTTP API and displays loaded models, activity status, and system metrics. See `spec.md` for the full specification.

**Status: Proof of concept / on hold.** The original goal was real-time tok/s monitoring, but `/api/ps` doesn't expose token throughput — see issue #12. The app can show loaded models, VRAM, activity detection, and CPU/RAM, but not tok/s.

## Tech stack

- **Python 3.13+** with **uv** for package management
- **Textual** — TUI framework (DataTable, Sparkline, ProgressBar)
- **aiohttp** — async HTTP client for Ollama API
- **psutil** — CPU and RAM metrics
- **SQLite** — local ring buffer for history (`~/.local/share/ollama-top/history.db`)

## Common commands

```bash
uv sync                  # install dependencies, create .venv
uv run ollama-top        # run the app
uv run ollama-top --host http://host:11434  # custom host
```

## Architecture

```
ollama_top/
├── __main__.py    # entry point: arg parsing, DB init, launch TUI
├── config.py      # host resolution ($OLLAMA_HOST / --host / default), constants
├── collector.py   # async OllamaCollector: polls /api/ps, /api/version, psutil
├── db.py          # SQLite schema, ring buffer insert/prune/query
└── tui.py         # Textual app: models table, sparkline, CPU/RAM bars
```

## Key conventions

- **No `print()`** — use `logging` for all output (`logger = logging.getLogger(__name__)`)
- **No GPU metrics** — intentionally omitted (requires sudo on macOS)
- **No proxy/intercept** — only observe via `/api/ps`, never make inference requests
- **Graceful degradation** — if Ollama is unreachable, show error and retry automatically
- **No tok/s** — `/api/ps` doesn't expose throughput; see issue #12 for details and possible workarounds

## Docker

- Base image: `cgr.dev/chainguard/python:latest-dev`
- Multi-stage build with uv
- Runtime user: `nonroot`
- Default `OLLAMA_HOST=http://host.docker.internal:11434`
