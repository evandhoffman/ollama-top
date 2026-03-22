# ollama-top

A `top`-like terminal UI for monitoring a locally running [Ollama](https://ollama.com) instance in real time.

Zero configuration, no proxy, no sudo — just run it and it works.

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

## Install

### pipx (recommended)

```bash
pipx install ollama-top
ollama-top
```

### Development

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

`--network host` lets the container reach Ollama on localhost. Alternatively, pass `--host` to specify the host explicitly.

## Configuration

| Method | Example |
|---|---|
| Environment variable | `OLLAMA_HOST=myhost:1234 ollama-top` |
| CLI flag | `ollama-top --host http://myhost:1234` |
| Default | `http://localhost:11434` |

The `--host` flag takes precedence over `$OLLAMA_HOST`.

## What it monitors

- **Loaded models** — name, size, VRAM usage, status (running/idle), expiry countdown
- **Throughput** — estimated tokens/sec with sparkline history
- **System** — CPU and RAM utilization

All data comes from Ollama's local HTTP API (`/api/ps`, `/api/version`) and `psutil`. No inference requests are made.

## Requirements

- Python >= 3.13
- Ollama running locally (or reachable over the network)
- macOS or Linux

## Known limitations

- Token/s is **estimated** from polling `/api/ps` status transitions, not measured directly
- GPU metrics are not available without sudo on macOS and are intentionally omitted
- VRAM numbers reflect Ollama's own reporting (model weights only)

## License

MIT
