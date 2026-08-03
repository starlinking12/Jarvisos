"""Shared types for the ModelRouter subsystem.

Every provider (Ollama, mock, future OpenAI-compatible/local-llama.cpp
providers) speaks this vocabulary — `ChatMessage`, `ModelCapabilities`,
`StreamChunk` — so `ModelRouter` never needs provider-specific branching.
This is the concrete expression of "every model must be replaceable" /
"no subsystem should depend directly on a specific model" from the project
mandate.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from jarvis_contracts import AiTaskType

# Re-exported so call sites only need to import from `jarvis_backend.ai.types`.
__all__ = [
    "AiTaskType",
    "ChatRole",
    "ChatMessage",
    "ModelCapabilities",
    "StreamChunk",
    "CompletionResult",
    "ProviderHealth",
    "ModelProvider",
    "RoutingDecision",
]


class ChatRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(slots=True, frozen=True)
class ChatMessage:
    role: ChatRole
    content: str
    # Present when role == TOOL: which tool call this message answers.
    tool_call_id: str | None = None
    # Present when the assistant message itself requests a tool call.
    tool_name: str | None = None


@dataclass(slots=True, frozen=True)
class ModelCapabilities:
    """What a specific (provider, model) pair can actually do. `ModelRouter`
    uses this to validate a routing target before committing to it, rather
    than discovering incompatibility mid-stream."""

    supports_streaming: bool
    supports_tool_calls: bool
    supports_embeddings: bool
    max_context_tokens: int


@dataclass(slots=True, frozen=True)
class StreamChunk:
    """One token/delta emitted during a streaming completion."""

    delta: str
    index: int
    done: bool
    # Only meaningful when done=True.
    finish_reason: str | None = None
    total_tokens: int | None = None


@dataclass(slots=True, frozen=True)
class CompletionResult:
    """Non-streaming (or fully-accumulated) result of a completion call."""

    content: str
    finish_reason: str
    total_tokens: int | None
    latency_ms: float


@dataclass(slots=True, frozen=True)
class ProviderHealth:
    healthy: bool
    detail: str
    available_models: list[str] = field(default_factory=list)


class ModelProvider(Protocol):
    """Structural interface every provider implements. Using a `Protocol`
    rather than an ABC lets a provider be defined without importing this
    module at all (useful for keeping provider packages independently
    testable/replaceable), while still giving `ModelRouter` full static
    type checking against the interface.
    """

    name: str

    async def health_check(self) -> ProviderHealth: ...

    def capabilities(self, model: str) -> ModelCapabilities: ...

    async def stream_chat(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]: ...

    async def embed(self, model: str, text: str) -> list[float]: ...

    async def warm(self, model: str) -> None:
        """Proactively load `model` into the provider's runtime memory
        without generating a real completion, so the next real request
        doesn't pay first-token load latency. Providers with no such
        concept (e.g. always-hot hosted APIs) implement this as a no-op."""
        ...


@dataclass(slots=True, frozen=True)
class RoutingDecision:
    """The concrete (provider, model) pair `ModelRouter` selected for a
    given task type, plus which fallback position it came from — surfaced
    in `ai.request` events for observability."""

    task_type: AiTaskType
    provider_name: str
    model: str
    fallback_index: int
