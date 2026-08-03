"""SettingsRepository — durable key-value storage for user-editable
settings (theme/quality preferences, voice configuration overrides, etc.),
completing the Phase 4 mandate: "Settings gains persisted, user-editable
preferences" (Phase 1's `SettingsRoot` was explicitly read-only pending
this — see the Phase 1 architecture notes).

Deliberately a generic key-value store, not a fixed schema — the
renderer's Zustand slices decide what they persist and under what key
(see `apps/renderer/src/state/persistence.ts`); this repository only
guarantees durable, atomic get/set/list for whatever JSON-serializable
value a key maps to.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from ..database import Database


class SettingsRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def get(self, key: str) -> Any | None:
        row = await self._db.fetch_one("SELECT value_json FROM settings WHERE key = ?", (key,))
        if row is None:
            return None
        return json.loads(row["value_json"])

    async def set(self, key: str, value: Any) -> None:
        await self._db.execute(
            """
            INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json,
                                            updated_at = excluded.updated_at
            """,
            (key, json.dumps(value), datetime.now(UTC).isoformat()),
        )

    async def delete(self, key: str) -> None:
        await self._db.execute("DELETE FROM settings WHERE key = ?", (key,))

    async def list_all(self) -> dict[str, Any]:
        rows = await self._db.fetch_all("SELECT key, value_json FROM settings")
        return {row["key"]: json.loads(row["value_json"]) for row in rows}
