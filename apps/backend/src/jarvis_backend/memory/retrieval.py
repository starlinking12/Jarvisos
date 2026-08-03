"""RetrievalPipeline — assembles the message context the Orchestrator hands
to `ModelRouter` for the final response, combining working memory,
long-term memory hits, and context compression.

Division of labor with `ContextWindowManager` (`ai/context_window.py`):
`RetrievalPipeline` decides WHAT should be considered (recency +
relevance policy — a retrieval concern) and applies coarse compression
when the working-memory buffer itself has grown large; `ContextWindowManager`
decides the final HARD token fit for whichever specific model
`ModelRouter` resolves to (a routing-time concern, since different
fallback targets may have different context windows). Neither duplicates
the other: retrieval policy doesn't know about model token budgets, and
`ContextWindowManager` doesn't know about long-term memory or
summarization.
"""

from __future__ import annotations

import uuid

import structlog
from jarvis_contracts import AiTaskType

from jarvis_backend.ai import ChatMessage, ChatRole, ModelRouter

from .long_term import LongTermMemory
from .types import MemoryItem
from .working_memory import WorkingMemory

logger = structlog.get_logger("jarvis_backend.memory.retrieval")

# Once working memory exceeds this many messages, the oldest portion is
# compressed into a single summary message rather than sent verbatim —
# keeps the message list bounded even across very long conversations,
# ahead of (and independent of) ModelRouter's final per-model token fit.
DEFAULT_COMPRESSION_THRESHOLD = 24
DEFAULT_COMPRESS_OLDEST_COUNT = 12


class RetrievalPipeline:
    def __init__(
        self,
        *,
        working_memory: WorkingMemory,
        long_term_memory: LongTermMemory,
        model_router: ModelRouter,
        compression_threshold: int = DEFAULT_COMPRESSION_THRESHOLD,
        compress_oldest_count: int = DEFAULT_COMPRESS_OLDEST_COUNT,
    ) -> None:
        self.working_memory = working_memory
        self._long_term_memory = long_term_memory
        self._model_router = model_router
        self._compression_threshold = compression_threshold
        self._compress_oldest_count = compress_oldest_count

    async def retrieve(self, conversation_id: uuid.UUID) -> list[ChatMessage]:
        messages = self.working_memory.get(conversation_id)

        if len(messages) > self._compression_threshold:
            messages = await self._compress(conversation_id, messages)

        long_term_hits = await self._retrieve_long_term(messages)
        if long_term_hits:
            messages = [
                ChatMessage(
                    role=ChatRole.SYSTEM,
                    content="Relevant prior context:\n"
                    + "\n".join(f"- {item.content}" for item in long_term_hits),
                ),
                *messages,
            ]

        return messages

    async def _compress(
        self, conversation_id: uuid.UUID, messages: list[ChatMessage]
    ) -> list[ChatMessage]:
        oldest = messages[: self._compress_oldest_count]
        remainder = messages[self._compress_oldest_count :]

        transcript = "\n".join(f"{m.role.value}: {m.content}" for m in oldest)
        summary_result = await self._model_router.complete(
            AiTaskType.SUMMARIZE,
            [
                ChatMessage(
                    role=ChatRole.SYSTEM,
                    content="Summarize the following conversation excerpt in 2-3 sentences, "
                    "preserving concrete facts, decisions, and unresolved questions.",
                ),
                ChatMessage(role=ChatRole.USER, content=transcript),
            ],
        )

        logger.info(
            "working_memory_compressed",
            conversation_id=str(conversation_id),
            compressed_message_count=len(oldest),
        )

        summary_message = ChatMessage(
            role=ChatRole.SYSTEM,
            content=f"Earlier in this conversation: {summary_result.content}",
        )
        return [summary_message, *remainder]

    async def _retrieve_long_term(self, recent_messages: list[ChatMessage]) -> list[MemoryItem]:
        if not recent_messages:
            return []
        query = recent_messages[-1].content
        return await self._long_term_memory.retrieve(query, limit=5)
