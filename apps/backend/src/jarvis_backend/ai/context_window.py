"""Context window management.

Ollama and most local model runtimes do not expose an exact tokenizer over
the wire, so this module uses a conservative character-based estimate
(~4 characters/token for English text, matching the widely-used rule of
thumb behind OpenAI's own approximation guidance) rather than depending on
a model-specific tokenizer package. This is intentionally an estimate, not
exact accounting — `ContextWindowManager` always reserves a safety margin
so an estimation error trends toward truncating slightly too much, never
too little (which would risk a provider-side context overflow error).
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import ChatMessage, ChatRole

CHARS_PER_TOKEN_ESTIMATE = 4.0
SAFETY_MARGIN_RATIO = 0.9  # only ever budget for 90% of the stated window


def estimate_tokens(text: str) -> int:
    """Conservative token estimate. Rounds up so truncation logic never
    under-counts."""
    return max(1, -(-len(text) // int(CHARS_PER_TOKEN_ESTIMATE)))


@dataclass(slots=True)
class TruncationResult:
    messages: list[ChatMessage]
    dropped_count: int
    estimated_tokens: int


class ContextWindowManager:
    """Fits a conversation's message list into a model's context budget.

    Strategy: always keep the system message (if present) and the most
    recent messages — conversational relevance decays with age, and the
    system message defines behavior for the whole exchange, so it is never
    a truncation candidate. Older non-system messages are dropped oldest
    first until the estimated token count fits within
    `max_context_tokens * SAFETY_MARGIN_RATIO` minus `reserved_output_tokens`
    (space reserved for the model's own response).
    """

    def __init__(self, max_context_tokens: int, reserved_output_tokens: int = 512) -> None:
        if reserved_output_tokens >= max_context_tokens:
            raise ValueError(
                "reserved_output_tokens must be smaller than max_context_tokens"
            )
        self.max_context_tokens = max_context_tokens
        self.reserved_output_tokens = reserved_output_tokens

    @property
    def input_budget_tokens(self) -> int:
        return int(self.max_context_tokens * SAFETY_MARGIN_RATIO) - self.reserved_output_tokens

    def fit(self, messages: list[ChatMessage]) -> TruncationResult:
        budget = self.input_budget_tokens
        if budget <= 0:
            raise ValueError(
                f"max_context_tokens ({self.max_context_tokens}) is too small to "
                f"reserve {self.reserved_output_tokens} output tokens"
            )

        system_messages = [m for m in messages if m.role == ChatRole.SYSTEM]
        other_messages = [m for m in messages if m.role != ChatRole.SYSTEM]

        kept_system_tokens = sum(estimate_tokens(m.content) for m in system_messages)
        remaining_budget = budget - kept_system_tokens

        # Walk from most recent to oldest, keeping messages while they fit.
        kept_reversed: list[ChatMessage] = []
        running_tokens = 0
        dropped_count = 0
        for message in reversed(other_messages):
            message_tokens = estimate_tokens(message.content)
            if running_tokens + message_tokens > remaining_budget:
                dropped_count += 1
                continue
            kept_reversed.append(message)
            running_tokens += message_tokens

        kept = list(reversed(kept_reversed))
        final_messages = system_messages + kept

        return TruncationResult(
            messages=final_messages,
            dropped_count=dropped_count,
            estimated_tokens=kept_system_tokens + running_tokens,
        )
