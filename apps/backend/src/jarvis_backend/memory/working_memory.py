"""Working memory — the short-term, per-conversation message buffer every
Orchestrator turn reads from and appends to.

Bounded by message count (not tokens — token-precise fitting is
`ContextWindowManager`'s job, applied later by `ModelRouter` against the
actually-resolved model's budget; working memory's bound exists so an
extremely long-running conversation doesn't grow this in-process buffer
without limit). Storage is in-process and non-durable in Phase 2 — see
`long_term.py` for the durable counterpart landing in Phase 3.
"""

from __future__ import annotations

import uuid
from collections import defaultdict, deque

from jarvis_backend.ai import ChatMessage

DEFAULT_MAX_MESSAGES_PER_CONVERSATION = 200


class WorkingMemory:
    def __init__(
        self, max_messages_per_conversation: int = DEFAULT_MAX_MESSAGES_PER_CONVERSATION
    ) -> None:
        self._max_messages = max_messages_per_conversation
        self._conversations: dict[uuid.UUID, deque[ChatMessage]] = defaultdict(
            lambda: deque(maxlen=self._max_messages)
        )

    def append(self, conversation_id: uuid.UUID, message: ChatMessage) -> None:
        self._conversations[conversation_id].append(message)

    def get(self, conversation_id: uuid.UUID) -> list[ChatMessage]:
        return list(self._conversations.get(conversation_id, ()))

    def clear(self, conversation_id: uuid.UUID) -> None:
        self._conversations.pop(conversation_id, None)
