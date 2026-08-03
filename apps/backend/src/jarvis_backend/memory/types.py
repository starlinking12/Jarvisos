"""Shared types for the memory subsystem."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class MemoryItem:
    """A single retrievable unit of long-term memory. Defined now (Phase 2)
    so `LongTermMemory`'s interface is stable ahead of Phase 3's actual
    persistence/embedding-search implementation — see ADR-0007."""

    item_id: str
    content: str
    created_at: datetime
    relevance_score: float | None = None
    source: str | None = None
