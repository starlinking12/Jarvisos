"""SqliteLongTermMemory — the real implementation ADR-0007 promised
behind the `LongTermMemory` interface, replacing `NullLongTermMemory` in
`main.py`'s composition root. See ADR-0012 for the full design.

Semantic memory: every stored item is embedded via `ModelRouter`'s
`embed` task (ADR-0002) and persisted alongside its content
(`MemoryRepository`); retrieval ranks stored items by cosine similarity
to the query's own embedding — genuine semantic search, not keyword
matching.

Episodic memory: every stored item already carries `created_at`
(`MemoryItem`), so a simple recency-ordered or time-range query over the
same table serves episodic ("what happened, when") retrieval without a
separate storage mechanism — episodic and semantic memory are the same
underlying records, queried two different ways.

Knowledge graph: `add_relationship`/`related_items` expose
`MemoryRepository`'s edge table — a real, minimal graph (typed
relationships between memory items), scoped to what a single-user
assistant's memory needs rather than a general-purpose graph database
(see ADR-0012's Alternatives Considered).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

import numpy as np
import structlog

from jarvis_backend.ai import ModelRouter

from .long_term import LongTermMemory
from .types import MemoryItem

logger = structlog.get_logger("jarvis_backend.memory.sqlite_long_term_memory")


class MemoryRepositoryProtocol(Protocol):
    async def insert_item(self, item: MemoryItem, embedding: list[float] | None) -> None: ...
    async def all_items_with_embeddings(
        self,
    ) -> list[tuple[MemoryItem, list[float] | None]]: ...
    async def add_relationship(
        self, from_item_id: str, to_item_id: str, relation: str
    ) -> None: ...
    async def related_items(self, item_id: str) -> list[tuple[str, str]]: ...


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    vec_a, vec_b = np.array(a), np.array(b)
    denom = np.linalg.norm(vec_a) * np.linalg.norm(vec_b)
    if denom == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / denom)


class SqliteLongTermMemory(LongTermMemory):
    def __init__(self, repository: MemoryRepositoryProtocol, model_router: ModelRouter) -> None:
        self._repository = repository
        self._model_router = model_router

    async def retrieve(self, query: str, *, limit: int = 5) -> list[MemoryItem]:
        items_with_embeddings = await self._repository.all_items_with_embeddings()
        if not items_with_embeddings:
            return []

        try:
            query_embedding = await self._model_router.embed(query)
        except Exception:  # noqa: BLE001 - embedding failure must degrade to "no
            # semantic results," never propagate and break the caller's
            # conversational turn over a memory-subsystem failure.
            logger.warning("query_embedding_failed", exc_info=True)
            return []

        scored: list[tuple[float, MemoryItem]] = []
        for item, embedding in items_with_embeddings:
            if embedding is None:
                continue
            score = _cosine_similarity(query_embedding, embedding)
            scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            MemoryItem(
                item_id=item.item_id,
                content=item.content,
                created_at=item.created_at,
                relevance_score=score,
                source=item.source,
            )
            for score, item in scored[:limit]
        ]

    async def store(self, content: str, *, source: str | None = None) -> MemoryItem:
        item = MemoryItem(
            item_id=str(uuid.uuid4()),
            content=content,
            created_at=datetime.now(UTC),
            source=source,
        )

        embedding: list[float] | None = None
        try:
            embedding = await self._model_router.embed(content)
        except Exception:  # noqa: BLE001 - a failed embedding must still let the
            # item persist (content is still retrievable via recency/episodic
            # queries even without a vector for semantic search).
            logger.warning("store_embedding_failed", exc_info=True)

        await self._repository.insert_item(item, embedding)
        return item

    async def add_relationship(self, from_item_id: str, to_item_id: str, relation: str) -> None:
        """Records a typed edge between two memory items — the knowledge-
        graph capability. Not part of the base `LongTermMemory` interface
        (`NullLongTermMemory` has no graph to add edges to), so callers
        that specifically want graph structure depend on
        `SqliteLongTermMemory` directly, same as `RetrievalPipeline`
        depends on the base interface for the common retrieve/store path."""
        await self._repository.add_relationship(from_item_id, to_item_id, relation)

    async def related_items(self, item_id: str) -> list[tuple[str, str]]:
        return await self._repository.related_items(item_id)
