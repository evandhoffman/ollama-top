# ollama-top

> **Status: Proof of concept / on hold.** See [Known limitations](#known-limitations) below.

A `top`-like terminal UI for monitoring a locally running [Ollama](https://ollama.com) instance in real time.

## What it shows today

- **Loaded models** — name, size, VRAM usage, idle/running status, expiry countdown
- **Activity** — sparkline of active model count over time
- **System** — CPU and RAM utilization via psutil

All data comes from Ollama's local HTTP API (`/api/ps`, `/api/version`) and `psutil`.

## Install

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

## Configuration

| Method | Example |
|---|---|
| Environment variable | `OLLAMA_HOST=myhost:1234 ollama-top` |
| CLI flag | `ollama-top --host http://myhost:1234` |
| Default | `http://localhost:11434` |

The `--host` flag takes precedence over `$OLLAMA_HOST`.

## Requirements

- Python >= 3.13
- Ollama running locally (or reachable over the network)
- macOS or Linux

## Known limitations

**No real-time tokens/sec.** This was the primary goal of the project, but it turns out Ollama's `/api/ps` endpoint does not expose token throughput metrics. The `eval_count` and `eval_duration` fields that contain tok/s data are only available in the streaming response body of `/api/generate` and `/api/chat` — which means you'd need to either proxy all Ollama traffic or parse server logs. Proxying doesn't help for the Ollama Mac app (which talks directly to `localhost:11434`), and log parsing requires access to Ollama's process output. See [#12](https://github.com/evandhoffman/ollama-top/issues/12) for details.

Other limitations:
- GPU metrics are not available without sudo on macOS and are intentionally omitted
- VRAM numbers reflect Ollama's own reporting (model weights only)
- Model "running" status is detected by watching `expires_at` changes between polls, which is indirect and has a 1-second resolution

## License

MIT
