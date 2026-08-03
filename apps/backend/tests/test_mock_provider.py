from __future__ import annotations

from jarvis_backend.ai.mock_provider import MockProvider
from jarvis_backend.ai.types import ChatMessage, ChatRole


async def test_mock_provider_health_check_reports_healthy_by_default() -> None:
    provider = MockProvider()
    health = await provider.health_check()
    assert health.healthy is True
    assert "mock-small" in health.available_models


async def test_mock_provider_health_check_can_be_forced_unhealthy() -> None:
    provider = MockProvider(healthy=False)
    health = await provider.health_check()
    assert health.healthy is False


async def test_mock_provider_capabilities_reports_configured_context_window() -> None:
    provider = MockProvider(max_context_tokens=2048)
    caps = provider.capabilities("mock-small")
    assert caps.max_context_tokens == 2048
    assert caps.supports_streaming is True
    assert caps.supports_embeddings is True


async def test_mock_provider_stream_chat_yields_scripted_response_word_by_word() -> None:
    provider = MockProvider(scripted_response="hello there world")
    chunks = [
        chunk
        async for chunk in provider.stream_chat(
            "mock-small", [ChatMessage(role=ChatRole.USER, content="hi")]
        )
    ]

    non_final = [c for c in chunks if not c.done]
    final = [c for c in chunks if c.done]

    assert "".join(c.delta for c in non_final) == "hello there world"
    assert len(final) == 1
    assert final[0].finish_reason == "stop"
    assert final[0].total_tokens == 3


async def test_mock_provider_records_calls_for_assertions() -> None:
    provider = MockProvider()
    messages = [ChatMessage(role=ChatRole.USER, content="track me")]

    async for _ in provider.stream_chat("mock-small", messages):
        pass

    assert provider.calls == [messages]


async def test_mock_provider_embed_is_deterministic() -> None:
    provider = MockProvider()
    first = await provider.embed("mock-small", "the same text")
    second = await provider.embed("mock-small", "the same text")
    third = await provider.embed("mock-small", "different text")

    assert first == second
    assert first != third
    assert len(first) == 8


async def test_mock_provider_warm_is_a_no_op() -> None:
    provider = MockProvider()
    await provider.warm("mock-small")  # should not raise
