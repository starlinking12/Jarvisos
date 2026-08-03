"""Mock provider for tests.

Implements the `ModelProvider` protocol with no network dependency —
deterministic, fast, and fully controllable, so `ModelRouter`,
`Orchestrator`, and agent tests never require a running Ollama instance.
Structural typing (see `ai/types.py`) means this class needs no shared base
class with `OllamaProvider`; it satisfies the protocol by shape alone,
which is the whole point of "every model must be replaceable."
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from .types import ChatMessage, ModelCapabilities, ProviderHealth, StreamChunk


class MockProvider:
    name = "mock"

    def __init__(
        self,
        *,
        scripted_response: str = "This is a mock response.",
        healthy: bool = True,
        max_context_tokens: int = 8192,
        chunk_delay_s: float = 0.0,
    ) -> None:
        self.scripted_response = scripted_response
        self.healthy = healthy
        self.max_context_tokens = max_context_tokens
        self.chunk_delay_s = chunk_delay_s
        self.calls: list[list[ChatMessage]] = []

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=self.healthy,
            detail="mock provider" if self.healthy else "mock provider forced unhealthy",
            available_models=["mock-small", "mock-large"],
        )

    def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            supports_streaming=True,
            supports_tool_calls=True,
            supports_embeddings=True,
            max_context_tokens=self.max_context_tokens,
        )

    async def stream_chat(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        self.calls.append(messages)
        words = self.scripted_response.split(" ")
        for index, word in enumerate(words):
            if self.chunk_delay_s:
                await asyncio.sleep(self.chunk_delay_s)
            delta = word if index == 0 else f" {word}"
            yield StreamChunk(delta=delta, index=index, done=False)
        yield StreamChunk(
            delta="",
            index=len(words),
            done=True,
            finish_reason="stop",
            total_tokens=len(words),
        )

    async def embed(self, model: str, text: str) -> list[float]:
        # Deterministic pseudo-embedding derived from text length/hash so
        # tests can assert on stable output without a real embedding model.
        seed = sum(ord(c) for c in text) % 997
        return [((seed + i) % 101) / 100.0 for i in range(8)]

    async def warm(self, model: str) -> None:
        return None
