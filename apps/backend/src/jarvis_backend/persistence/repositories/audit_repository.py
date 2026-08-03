"""AuditRepository — durable persistence for `SafetyGate`'s permission
decision audit trail (ADR-0004 §Consequences).

Every permission check `SafetyGate` makes was already logged via
structlog since Phase 2; this repository adds a durable, queryable copy
in SQLite alongside the structured log stream — both exist because they
serve different consumers (structlog: real-time operational log
tailing/aggregation; this table: "show me every permission decision for
task X" queries a future Security Center UI can run without parsing log
files).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from ..database import Database


class AuditRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def record(
        self, *, event: str, correlation_id: str | None, payload: dict[str, Any]
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO audit_log (timestamp, event, correlation_id, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                datetime.now(UTC).isoformat(),
                event,
                correlation_id,
                json.dumps(payload),
            ),
        )

    async def list_for_correlation_id(
        self, correlation_id: str, limit: int = 200
    ) -> list[dict[str, Any]]:
        rows = await self._db.fetch_all(
            """
            SELECT timestamp, event, payload_json FROM audit_log
            WHERE correlation_id = ? ORDER BY id ASC LIMIT ?
            """,
            (correlation_id, limit),
        )
        return [
            {
                "timestamp": row["timestamp"],
                "event": row["event"],
                **json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    async def list_recent(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = await self._db.fetch_all(
            "SELECT timestamp, event, correlation_id, payload_json FROM audit_log "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [
            {
                "timestamp": row["timestamp"],
                "event": row["event"],
                "correlation_id": row["correlation_id"],
                **json.loads(row["payload_json"]),
            }
            for row in rows
        ]
