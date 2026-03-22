"""Configuration: Ollama host resolution and constants."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_HOST = "http://localhost:11434"
POLL_INTERVAL = 1.0
SPARKLINE_WIDTH = 20
DB_PATH = Path(os.environ.get("DB_PATH", Path.home() / ".local" / "share" / "ollama-top" / "history.db"))


def resolve_host(cli_host: str | None = None) -> str:
    """Resolve the Ollama API host URL.

    Priority:
      1. ``cli_host`` argument (e.g. from ``--host`` flag)
      2. ``$OLLAMA_HOST`` environment variable
      3. ``http://localhost:11434`` default

    Bare ``host:port`` values are normalised to include an ``http://`` scheme.
    """
    host: str | None = cli_host

    if host is None:
        host = os.environ.get("OLLAMA_HOST")
        if host is not None:
            logger.debug("Using OLLAMA_HOST from environment: %s", host)

    if host is None:
        logger.debug("No host specified; falling back to %s", DEFAULT_HOST)
        return DEFAULT_HOST

    host = host.strip()

    # Normalise bare host:port (no scheme) to http://
    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"http://{host}"
        logger.debug("Added http:// scheme: %s", host)

    # Strip trailing slash for consistency
    host = host.rstrip("/")

    logger.debug("Resolved Ollama host: %s", host)
    return host
