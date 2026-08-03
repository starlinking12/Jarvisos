from __future__ import annotations

import uuid
from datetime import UTC, datetime

from jarvis_backend.ai import ChatMessage, ChatRole, MockProvider, ModelRouter
from jarvis_backend.config import ResourceLimits, RetryPolicy
from jarvis_backend.event_bus import EventBus
from jarvis_backend.memory.long_term import LongTermMemory, NullLongTermMemory
from jarvis_backend.memory.retrieval import RetrievalPipeline
from jarvis_backend.memory.types import MemoryItem
from jarvis_backend.memory.working_memory import WorkingMemory

from .conftest import make_all_task_routing


def _make_router(scripted_response: str = "a summary") -> ModelRouter:
    provider = MockProvider(scripted_response=scripted_response)
    return ModelRouter(
        providers={"mock": provider},
        routing=make_all_task_routing(),
        retry_policy=RetryPolicy(max_retries=0),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=EventBus(),
    )


async def test_retrieve_returns_working_memory_verbatim_below_threshold() -> None:
    working_memory = WorkingMemory()
    conversation_id = uuid.uuid4()
    working_memory.append(conversation_id, ChatMessage(role=ChatRole.USER, content="hi"))

    pipeline = RetrievalPipeline(
        working_memory=working_memory,
        long_term_memory=NullLongTermMemory(),
        model_router=_make_router(),
    )

    result = await pipeline.retrieve(conversation_id)

    assert len(result) == 1
    assert result[0].content == "hi"


async def test_retrieve_compresses_when_over_threshold() -> None:
    working_memory = WorkingMemory()
    conversation_id = uuid.uuid4()
    for i in range(30):
        working_memory.append(
            conversation_id, ChatMessage(role=ChatRole.USER, content=f"msg {i}")
        )

    pipeline = RetrievalPipeline(
        working_memory=working_memory,
        long_term_memory=NullLongTermMemory(),
        model_router=_make_router(scripted_response="condensed summary"),
        compression_threshold=24,
        compress_oldest_count=12,
    )

    result = await pipeline.retrieve(conversation_id)

    # 12 oldest compressed into 1 summary message + 18 remaining verbatim.
    assert len(result) == 19
    assert result[0].role == ChatRole.SYSTEM
    assert "condensed summary" in result[0].content


async def test_retrieve_prepends_long_term_hits_when_present() -> None:
    class _StubLongTermMemory(LongTermMemory):
        async def retrieve(self, query: str, *, limit: int = 5) -> list[MemoryItem]:
            return [
                MemoryItem(
                    item_id="1",
                    content="the user prefers dark mode",
                    created_at=datetime.now(UTC),
                )
            ]

        async def store(self, content: str, *, source: str | None = None) -> MemoryItem:
            return MemoryItem(item_id="x", content=content, created_at=datetime.now(UTC))

    working_memory = WorkingMemory()
    conversation_id = uuid.uuid4()
    working_memory.append(conversation_id, ChatMessage(role=ChatRole.USER, content="hi"))

    pipeline = RetrievalPipeline(
        working_memory=working_memory,
        long_term_memory=_StubLongTermMemory(),
        model_router=_make_router(),
    )

    result = await pipeline.retrieve(conversation_id)

    assert result[0].role == ChatRole.SYSTEM
    assert "dark mode" in result[0].content
    assert result[-1].content == "hi"


async def test_null_long_term_memory_retrieve_returns_empty() -> None:
    memory = NullLongTermMemory()
    assert await memory.retrieve("anything") == []


async def test_null_long_term_memory_store_returns_well_formed_item() -> None:
    memory = NullLongTermMemory()
    item = await memory.store("some content", source="test")

    assert item.content == "some content"
    assert item.source == "test"
    assert item.item_id
