from __future__ import annotations

import pytest

from jarvis_backend.ai.context_window import ContextWindowManager, estimate_tokens
from jarvis_backend.ai.types import ChatMessage, ChatRole


def test_estimate_tokens_is_conservative_and_rounds_up() -> None:
    assert estimate_tokens("abcd") == 1  # exactly 4 chars -> 1 token
    assert estimate_tokens("abcde") == 2  # 5 chars -> rounds up to 2 tokens
    assert estimate_tokens("") == 1  # never returns zero


def test_fit_keeps_system_message_and_recent_messages() -> None:
    manager = ContextWindowManager(max_context_tokens=200, reserved_output_tokens=50)
    messages = [
        ChatMessage(role=ChatRole.SYSTEM, content="You are JARVIS."),
        ChatMessage(role=ChatRole.USER, content="old message " * 10),
        ChatMessage(role=ChatRole.ASSISTANT, content="old reply " * 10),
        ChatMessage(role=ChatRole.USER, content="recent message"),
    ]

    result = manager.fit(messages)

    assert result.messages[0].role == ChatRole.SYSTEM
    assert result.messages[-1].content == "recent message"


def test_fit_drops_oldest_non_system_messages_first() -> None:
    manager = ContextWindowManager(max_context_tokens=60, reserved_output_tokens=10)
    messages = [ChatMessage(role=ChatRole.USER, content=f"message number {i}") for i in range(20)]

    result = manager.fit(messages)

    assert result.dropped_count > 0
    kept_contents = [m.content for m in result.messages]
    assert "message number 19" in kept_contents  # most recent always kept
    assert "message number 0" not in kept_contents  # oldest dropped first


def test_fit_raises_if_budget_too_small_for_reserved_output() -> None:
    with pytest.raises(ValueError):
        ContextWindowManager(max_context_tokens=100, reserved_output_tokens=100)


def test_input_budget_respects_safety_margin() -> None:
    manager = ContextWindowManager(max_context_tokens=1000, reserved_output_tokens=0)
    # SAFETY_MARGIN_RATIO = 0.9, so budget should be 900, not 1000.
    assert manager.input_budget_tokens == 900
