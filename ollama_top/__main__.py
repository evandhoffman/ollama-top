"""Entry point for ollama-top."""

import argparse
import asyncio
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

    from ollama_top.collector import OllamaCollector
    from ollama_top.config import resolve_host
    from ollama_top.db import Database
    from ollama_top.tui import OllamaTop

    host = resolve_host(args.host)
    logger.info("ollama-top starting — target %s", host)

    collector = OllamaCollector(host)
    db = Database()
    app = OllamaTop(collector)

    async def _init_db() -> None:
        await db.init()

    asyncio.run(_init_db())

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        # Clean up resources
        async def _shutdown() -> None:
            await collector.close()
            await db.close()

        asyncio.run(_shutdown())
        logger.info("ollama-top stopped")


if __name__ == "__main__":
    main()
