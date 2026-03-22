"""Entry point for ollama-top."""

import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor a local Ollama instance")
    parser.add_argument("--host", help="Ollama host URL (overrides $OLLAMA_HOST)")
    args = parser.parse_args()
    logger.info("ollama-top starting (host=%s)", args.host or "default")


if __name__ == "__main__":
    main()
