from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from jarvis_contracts import AiTaskType

from jarvis_backend.ai.mock_provider import MockProvider
from jarvis_backend.ai.router import ModelRouter, NoHealthyProviderError
from jarvis_backend.ai.types import (
    ChatMessage,
    ChatRole,
    ModelCapabilities,
    ProviderHealth,
    StreamChunk,
)
from jarvis_backend.config import (
    ResourceLimits,
    RetryPolicy,
    RoutingConfig,
    RoutingRule,
    RoutingTarget,
)
from jarvis_backend.event_bus import EventBus


class _AlwaysFailingProvider:
    """A provider that fails every call — used to exercise the fallback
    chain without relying on network conditions."""

    name = "failing"

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(healthy=False, detail="always fails")

    def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            supports_streaming=True,
            supports_tool_calls=True,
            supports_embeddings=True,
            max_context_tokens=8192,
        )

    async def stream_chat(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        raise RuntimeError("simulated provider failure")
        yield  # pragma: no cover - makes this an async generator

    async def embed(self, model: str, text: str) -> list[float]:
        raise RuntimeError("simulated provider failure")

    async def warm(self, model: str) -> None:
        return None


class _NoStreamingProvider(MockProvider):
    def capabilities(self, model: str) -> ModelCapabilities:
        caps = super().capabilities(model)
        return ModelCapabilities(
            supports_streaming=False,
            supports_tool_calls=caps.supports_tool_calls,
            supports_embeddings=caps.supports_embeddings,
            max_context_tokens=caps.max_context_tokens,
        )


def _single_target_routing(provider: str, model: str = "mock-small") -> RoutingConfig:
    return RoutingConfig(
        rules=[
            RoutingRule(task_type=t, targets=[RoutingTarget(provider=provider, model=model)])
            for t in AiTaskType
        ]
    )


def _fallback_routing(providers_in_order: list[str], model: str = "mock-small") -> RoutingConfig:
    targets = [RoutingTarget(provider=p, model=model) for p in providers_in_order]
    return RoutingConfig(rules=[RoutingRule(task_type=t, targets=targets) for t in AiTaskType])


async def test_stream_yields_scripted_deltas_from_mock_provider() -> None:
    provider = MockProvider(scripted_response="the answer is 42")
    router = ModelRouter(
        providers={"mock": provider},
        routing=_single_target_routing("mock"),
        retry_policy=RetryPolicy(max_retries=0),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=EventBus(),
    )

    deltas = [
        d
        async for d in router.stream(
            AiTaskType.CHAT, [ChatMessage(role=ChatRole.USER, content="hi")]
        )
    ]

    assert "".join(deltas) == "the answer is 42"


async def test_stream_falls_back_to_next_target_on_failure() -> None:
    failing = _AlwaysFailingProvider()
    working = MockProvider(scripted_response="fallback worked")
    router = ModelRouter(
        providers={"failing": failing, "mock": working},
        routing=_fallback_routing(["failing", "mock"]),
        retry_policy=RetryPolicy(max_retries=0, base_backoff_s=0.01, max_backoff_s=0.02),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=EventBus(),
    )

    deltas = [
        d
        async for d in router.stream(
            AiTaskType.CHAT, [ChatMessage(role=ChatRole.USER, content="hi")]
        )
    ]

    assert "".join(deltas) == "fallback worked"


async def test_stream_raises_when_every_target_fails() -> None:
    router = ModelRouter(
        providers={"failing": _AlwaysFailingProvider()},
        routing=_single_target_routing("failing"),
        retry_policy=RetryPolicy(max_retries=0, base_backoff_s=0.01, max_backoff_s=0.02),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=EventBus(),
    )

    with pytest.raises(NoHealthyProviderError):
        async for _ in router.stream(
            AiTaskType.CHAT, [ChatMessage(role=ChatRole.USER, content="hi")]
        ):
            pass


async def test_stream_skips_target_lacking_streaming_capability() -> None:
    no_streaming = _NoStreamingProvider(scripted_response="should not be used")
    fallback = MockProvider(scripted_response="capability negotiation worked")
    router = ModelRouter(
        providers={"no-stream": no_streaming, "mock": fallback},
        routing=_fallback_routing(["no-stream", "mock"]),
        retry_policy=RetryPolicy(max_retries=0),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=EventBus(),
    )

    deltas = [
        d
        async for d in router.stream(
            AiTaskType.CHAT, [ChatMessage(role=ChatRole.USER, content="hi")]
        )
    ]

    assert "".join(deltas) == "capability negotiation worked"


async def test_stream_publishes_ai_request_token_response_events() -> None:
    provider = MockProvider(scripted_response="two words")
    bus = EventBus()
    received: list[str] = []

    async def collect() -> None:
        async for event in bus.subscribe():
            received.append(event.type)
            if event.type == "ai.response":
                return

    router = ModelRouter(
        providers={"mock": provider},
        routing=_single_target_routing("mock"),
        retry_policy=RetryPolicy(max_retries=0),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=bus,
    )

    collector_task = asyncio.create_task(collect())
    await asyncio.sleep(0)  # let the subscriber register before publishing starts
    async for _ in router.stream(AiTaskType.CHAT, [ChatMessage(role=ChatRole.USER, content="hi")]):
        pass
    await asyncio.wait_for(collector_task, timeout=2)

    assert received[0] == "ai.request"
    assert "ai.token" in received
    assert received[-1] == "ai.response"


async def test_complete_accumulates_full_stream() -> None:
    provider = MockProvider(scripted_response="full text response")
    router = ModelRouter(
        providers={"mock": provider},
        routing=_single_target_routing("mock"),
        retry_policy=RetryPolicy(max_retries=0),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=EventBus(),
    )

    result = await router.complete(
        AiTaskType.SUMMARIZE, [ChatMessage(role=ChatRole.USER, content="hi")]
    )

    assert result.content == "full text response"
    assert result.latency_ms >= 0


async def test_embed_returns_provider_embedding() -> None:
    provider = MockProvider()
    router = ModelRouter(
        providers={"mock": provider},
        routing=_single_target_routing("mock"),
        retry_policy=RetryPolicy(max_retries=0),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=EventBus(),
    )

    embedding = await router.embed("some text")
    assert len(embedding) == 8
