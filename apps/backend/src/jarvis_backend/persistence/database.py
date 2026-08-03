"""Database — the single durable local-first SQLite store backing every
Phase 4 persistence need: long-term memory, task history, audit logs,
security alerts, and user settings.

One SQLite file, one `Database` instance, shared across every repository
(`TaskRepository`, `AuditRepository`, `MemoryRepository`,
`SettingsRepository`, `SecurityRepository`) — consistent with this
project's "one composition root constructs shared infrastructure once"
pattern (`EventBus` is the same shape: a single instance, injected
everywhere it's needed, never re-instantiated per subsystem).

**Why SQLite, not a client-server database:** "local-first,"
"offline-first," and "privacy-by-default" (project mandate) all point the
same direction — a single embedded file requires no separate server
process, no network configuration, and no additional attack surface, and
is fully sufficient for a single-user desktop assistant's data volume.
`aiosqlite` gives this an async-native interface consistent with the rest
of the backend's asyncio architecture, rather than blocking the event
loop on every query.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite
import structlog

logger = structlog.get_logger("jarvis_backend.persistence.database")

DEFAULT_DB_PATH = Path.home() / ".jarvis" / "jarvis.db"

# Every table this project persists to, in one place — see each
# repository module for the queries that read/write these tables. Kept
# together (not split per-repository) so the full schema is reviewable at
# a glance and migrations never apply out of dependency order.
SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        goal TEXT NOT NULL,
        requested_by TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        summary TEXT,
        plan_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS task_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL REFERENCES tasks(task_id),
        step_id TEXT NOT NULL,
        success INTEGER NOT NULL,
        detail TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_task_observations_task_id ON task_observations(task_id)",
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        event TEXT NOT NULL,
        correlation_id TEXT,
        payload_json TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_log_correlation_id ON audit_log(correlation_id)",
    """
    CREATE TABLE IF NOT EXISTS memory_items (
        item_id TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        source TEXT,
        embedding BLOB
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_item_id TEXT NOT NULL REFERENCES memory_items(item_id),
        to_item_id TEXT NOT NULL REFERENCES memory_items(item_id),
        relation TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_memory_edges_from ON memory_edges(from_item_id)",
    "CREATE INDEX IF NOT EXISTS idx_memory_edges_to ON memory_edges(to_item_id)",
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS security_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        severity TEXT NOT NULL,
        category TEXT NOT NULL,
        message TEXT NOT NULL,
        requires_approval INTEGER NOT NULL,
        resolved INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS file_integrity_baseline (
        path TEXT PRIMARY KEY,
        file_hash TEXT NOT NULL,
        last_checked TEXT NOT NULL
    )
    """,
)


class Database:
    def __init__(self, path: Path = DEFAULT_DB_PATH) -> None:
        self._path = path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self._connection is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(str(self._path))
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._migrate()
        logger.info("database_connected", path=str(self._path))

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            logger.info("database_closed")

    async def _migrate(self) -> None:
        assert self._connection is not None
        for statement in SCHEMA_STATEMENTS:
            await self._connection.execute(statement)
        await self._connection.commit()

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database.connect() must be called before use")
        return self._connection

    async def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        await self.connection.execute(query, params)
        await self.connection.commit()

    async def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        cursor = await self.connection.execute(query, params)
        return await cursor.fetchone()

    async def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        cursor = await self.connection.execute(query, params)
        return list(await cursor.fetchall())
