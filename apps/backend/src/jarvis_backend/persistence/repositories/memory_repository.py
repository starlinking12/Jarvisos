"""MemoryRepository — durable storage backing the real `LongTermMemory`
implementation (`memory/long_term.py`'s `SqliteLongTermMemory`).

Two tables: `memory_items` (the semantic memory store — content +
embedding vector, BLOB-serialized) and `memory_edges` (a minimal
knowledge graph — typed relationships between items). This is a real,
functioning knowledge graph at the scope this project's data volume
needs (a single user's assistant memory, not a general-purpose graph
database) — see ADR-0012 for why a full graph database was not adopted.
"""

from __future__ import annotations

import struct
from datetime import datetime

from jarvis_backend.memory.types import MemoryItem

from ..database import Database


def _embedding_to_blob(embedding: list[float]) -> bytes:
    return struct.pack(f"<{len(embedding)}f", *embedding)


def _blob_to_embedding(blob: bytes) -> list[float]:
    count = len(blob) // 4
    return list(struct.unpack(f"<{count}f", blob))


class MemoryRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def insert_item(self, item: MemoryItem, embedding: list[float] | None) -> None:
        await self._db.execute(
            """
            INSERT INTO memory_items (item_id, content, created_at, source, embedding)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item.item_id,
                item.content,
                item.created_at.isoformat(),
                item.source,
                _embedding_to_blob(embedding) if embedding is not None else None,
            ),
        )

    async def all_items_with_embeddings(self) -> list[tuple[MemoryItem, list[float] | None]]:
        rows = await self._db.fetch_all("SELECT * FROM memory_items ORDER BY created_at DESC")
        results = []
        for row in rows:
            item = MemoryItem(
                item_id=row["item_id"],
                content=row["content"],
                created_at=datetime.fromisoformat(row["created_at"]),
                source=row["source"],
            )
            embedding = _blob_to_embedding(row["embedding"]) if row["embedding"] else None
            results.append((item, embedding))
        return results

    async def add_relationship(self, from_item_id: str, to_item_id: str, relation: str) -> None:
        await self._db.execute(
            """
            INSERT INTO memory_edges (from_item_id, to_item_id, relation, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (from_item_id, to_item_id, relation, datetime.now().isoformat()),
        )

    async def related_items(self, item_id: str) -> list[tuple[str, str]]:
        """Returns `(related_item_id, relation)` pairs for every edge
        touching `item_id`, in either direction."""
        rows = await self._db.fetch_all(
            """
            SELECT to_item_id AS other, relation FROM memory_edges WHERE from_item_id = ?
            UNION
            SELECT from_item_id AS other, relation FROM memory_edges WHERE to_item_id = ?
            """,
            (item_id, item_id),
        )
        return [(row["other"], row["relation"]) for row in rows]

    async def item_count(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) AS count FROM memory_items")
        return int(row["count"]) if row is not None else 0
