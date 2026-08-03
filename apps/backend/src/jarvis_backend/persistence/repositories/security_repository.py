"""SecurityRepository — durable storage for the Security Center
(`security/`): every `security.alert` is persisted here (the event
itself is also published live over the `EventBus`, per the same
"structlog/event-bus for real-time, SQLite for durable+queryable" split
`AuditRepository` documents), plus the file-integrity monitor's baseline
hashes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..database import Database


class SecurityRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def insert_alert(
        self, *, severity: str, category: str, message: str, requires_approval: bool
    ) -> int:
        await self._db.execute(
            """
            INSERT INTO security_alerts (timestamp, severity, category, message, requires_approval)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datetime.now(UTC).isoformat(),
                severity,
                category,
                message,
                1 if requires_approval else 0,
            ),
        )
        row = await self._db.fetch_one("SELECT last_insert_rowid() AS id")
        return int(row["id"]) if row is not None else -1

    async def resolve_alert(self, alert_id: int) -> None:
        await self._db.execute(
            "UPDATE security_alerts SET resolved = 1 WHERE id = ?", (alert_id,)
        )

    async def list_recent_alerts(
        self, *, unresolved_only: bool = False, limit: int = 100
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM security_alerts"
        if unresolved_only:
            query += " WHERE resolved = 0"
        query += " ORDER BY id DESC LIMIT ?"
        rows = await self._db.fetch_all(query, (limit,))
        return [dict(row) for row in rows]

    async def get_file_baseline(self, path: str) -> str | None:
        row = await self._db.fetch_one(
            "SELECT file_hash FROM file_integrity_baseline WHERE path = ?", (path,)
        )
        return row["file_hash"] if row is not None else None

    async def set_file_baseline(self, path: str, file_hash: str) -> None:
        await self._db.execute(
            """
            INSERT INTO file_integrity_baseline (path, file_hash, last_checked)
            VALUES (?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET file_hash = excluded.file_hash,
                                             last_checked = excluded.last_checked
            """,
            (path, file_hash, datetime.now(UTC).isoformat()),
        )

    async def all_baseline_paths(self) -> list[str]:
        rows = await self._db.fetch_all("SELECT path FROM file_integrity_baseline")
        return [row["path"] for row in rows]
