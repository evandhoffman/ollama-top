"""SQLite schema and ring buffer queries."""

import logging
from datetime import datetime, timezone

import aiosqlite

from ollama_top.config import DB_PATH

logger = logging.getLogger(__name__)

_MAX_ROWS = 1000


class Database:
    """Async SQLite database for storing model snapshots and throughput history."""

    def __init__(self, path: str | None = None) -> None:
        self._path = str(path or DB_PATH)
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Create parent directories, open connection, and create tables."""
        from pathlib import Path

        parent = Path(self._path).parent
        parent.mkdir(parents=True, exist_ok=True)
        logger.info("Opening database at %s", self._path)

        self._db = await aiosqlite.connect(self._path)
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                timestamp   TEXT    NOT NULL,
                model_name  TEXT    NOT NULL,
                status      TEXT    NOT NULL,
                vram_bytes  INTEGER NOT NULL
            )
            """
        )
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS throughput (
                timestamp       TEXT NOT NULL,
                tokens_per_sec  REAL NOT NULL
            )
            """
        )
        await self._db.commit()
        logger.info("Database tables ready")

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Inserts with ring-buffer pruning
    # ------------------------------------------------------------------

    async def insert_snapshot(
        self, model_name: str, status: str, vram_bytes: int
    ) -> None:
        """Insert a model snapshot and prune oldest rows beyond the limit."""
        assert self._db is not None
        ts = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO snapshots (timestamp, model_name, status, vram_bytes) "
            "VALUES (?, ?, ?, ?)",
            (ts, model_name, status, vram_bytes),
        )
        await self._prune("snapshots")
        await self._db.commit()

    async def insert_throughput(self, tokens_per_sec: float) -> None:
        """Insert a throughput sample and prune oldest rows beyond the limit."""
        assert self._db is not None
        ts = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO throughput (timestamp, tokens_per_sec) VALUES (?, ?)",
            (ts, tokens_per_sec),
        )
        await self._prune("throughput")
        await self._db.commit()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_recent_throughput(self, n: int = 20) -> list[float]:
        """Return the *n* most recent throughput values, oldest first."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT tokens_per_sec FROM throughput "
            "ORDER BY rowid DESC LIMIT ?",
            (n,),
        )
        rows = await cursor.fetchall()
        # Rows come back newest-first; reverse so the list is oldest-first
        # (suitable for a sparkline where the rightmost value is the latest).
        return [row[0] for row in reversed(rows)]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _prune(self, table: str) -> None:
        """Delete the oldest rows when the table exceeds _MAX_ROWS."""
        assert self._db is not None
        await self._db.execute(
            f"DELETE FROM {table} WHERE rowid NOT IN "  # noqa: S608
            f"(SELECT rowid FROM {table} ORDER BY rowid DESC LIMIT ?)",
            (_MAX_ROWS,),
        )
