"""Long-term memory interface (see ADR-0007).

`LongTermMemory` is defined now, in Phase 2, so `RetrievalPipeline` and the
Orchestrator can be written against a stable interface — Phase 3 swaps in a
real persistence/embedding-search implementation (episodic + semantic
memory, knowledge graph, per the project mandate) without touching any
caller. `NullLongTermMemory` is the Phase 2 default: a genuine null-object
implementation (always returns no results, always accepts and discards
writes) satisfying the interface — not a stub that raises
`NotImplementedError`, because a caller that unconditionally awaits
`retrieve()` should never have to special-case "long-term memory isn't
built yet." That would leak a Phase 3 implementation detail into Phase 2
call sites, which is exactly the coupling this interface exists to avoid.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from .types import MemoryItem


class LongTermMemory(ABC):
    @abstractmethod
    async def retrieve(self, query: str, *, limit: int = 5) -> list[MemoryItem]:
        """Returns up to `limit` memory items relevant to `query`, ordered
        by descending relevance."""

    @abstractmethod
    async def store(self, content: str, *, source: str | None = None) -> MemoryItem:
        """Persists `content` as a new memory item and returns it."""


class NullLongTermMemory(LongTermMemory):
    async def retrieve(self, query: str, *, limit: int = 5) -> list[MemoryItem]:
        return []

    async def store(self, content: str, *, source: str | None = None) -> MemoryItem:
        # Intentionally a real, well-formed MemoryItem — callers that log
        # or display "what was stored" get a coherent object, even though
        # nothing is actually persisted past process lifetime yet.
        return MemoryItem(
            item_id=str(uuid.uuid4()),
            content=content,
            created_at=datetime.now(UTC),
            source=source,
        )
