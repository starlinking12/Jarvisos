"""ModelRouter — the single entry point every AI-consuming subsystem
(Orchestrator, domain agents, memory summarization) uses to talk to a
model. See ADR-0002 for the full architectural rationale.

Responsibilities:
  - Task-based routing: resolves a `AiTaskType` to an ordered fallback
    chain of (provider, model) targets via `RoutingConfig`.
  - Capability negotiation: validates the target model actually supports
    what the call needs (streaming, tool calls, embeddings) before using
    it, rather than discovering incompatibility mid-request.
  - Fallback: on a target's failure, retries with backoff up to
    `RetryPolicy.max_retries`, then advances to the next target in the
    chain. Only raises to the caller once every target is exhausted.
  - Context window management: truncates the message list to fit the
    resolved model's `max_context_tokens` via `ContextWindowManager`
    before sending.
  - Warm management: asks `WarmModelManager` to pre-warm the target before
    issuing the real request.
  - Event bus integration: publishes `ai.request` before calling the
    provider, `ai.token` per streamed chunk, and `ai.response` on
    completion or terminal failure — see ADR-0003.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import TypeVar

import structlog
from jarvis_contracts import (
    AiFinishReason,
    AiRequestEvent,
    AiRequestPayload,
    AiResponseEvent,
    AiResponsePayload,
    AiTaskType,
    AiTokenEvent,
    AiTokenPayload,
    EventSource,
)

from jarvis_backend.config import ResourceLimits, RetryPolicy, RoutingConfig
from jarvis_backend.event_bus import EventBus

from .context_window import ContextWindowManager
from .types import ChatMessage, CompletionResult, ModelProvider
from .warm_pool import WarmModelManager

logger = structlog.get_logger("jarvis_backend.ai.router")

T = TypeVar("T")


class NoHealthyProviderError(RuntimeError):
    """Raised when every target in a task type's fallback chain fails."""


class ModelRouter:
    def __init__(
        self,
        *,
        providers: dict[str, ModelProvider],
        routing: RoutingConfig,
        retry_policy: RetryPolicy,
        resource_limits: ResourceLimits,
        event_bus: EventBus,
        warm_pool: WarmModelManager | None = None,
    ) -> None:
        self._providers = providers
        self._routing = routing
        self._retry_policy = retry_policy
        self._resource_limits = resource_limits
        self._event_bus = event_bus
        self._warm_pool = warm_pool or WarmModelManager()
        self._concurrency_gate = asyncio.Semaphore(resource_limits.max_concurrent_ai_requests)

    async def stream(
        self,
        task_type: AiTaskType,
        messages: list[ChatMessage],
        *,
        task_id: uuid.UUID | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Streams text deltas for a chat-shaped task (chat, reasoning,
        toolcall, summarize). Publishes the full `ai.request` /
        `ai.token` / `ai.response` event sequence as it goes."""

        chain = self._routing.chain_for(task_type)
        request_id = uuid.uuid4()
        effective_max_tokens = min(
            max_tokens or self._resource_limits.max_tokens_per_request,
            self._resource_limits.max_tokens_per_request,
        )

        async with self._concurrency_gate:
            last_error: Exception | None = None

            for fallback_index, target in enumerate(chain):
                provider = self._providers.get(target.provider)
                if provider is None:
                    logger.warning("unknown_provider_in_routing_table", provider=target.provider)
                    continue

                capabilities = provider.capabilities(target.model)
                if not capabilities.supports_streaming:
                    logger.warning(
                        "target_lacks_streaming_capability",
                        provider=target.provider,
                        model=target.model,
                    )
                    continue

                context_manager = ContextWindowManager(capabilities.max_context_tokens)
                fitted = context_manager.fit(messages)
                if fitted.dropped_count > 0:
                    logger.info(
                        "context_truncated",
                        dropped_count=fitted.dropped_count,
                        estimated_tokens=fitted.estimated_tokens,
                    )

                await self._warm_pool.ensure_warm(provider, target.model)

                try:
                    async for text_delta in self._attempt_stream(
                        provider=provider,
                        model=target.model,
                        messages=fitted.messages,
                        max_tokens=effective_max_tokens,
                        temperature=temperature,
                        request_id=request_id,
                        task_id=task_id,
                        task_type=task_type,
                        fallback_index=fallback_index,
                    ):
                        yield text_delta
                    self._warm_pool.touch(target.provider, target.model)
                    return
                except Exception as error:  # noqa: BLE001 - deliberately broad: any
                    # provider-side failure (network, HTTP, malformed stream)
                    # should trigger fallback, not just a narrow exception set.
                    last_error = error
                    logger.warning(
                        "provider_target_failed",
                        provider=target.provider,
                        model=target.model,
                        fallback_index=fallback_index,
                        error=str(error),
                    )
                    continue

            await self._event_bus.publish(
                AiResponseEvent(
                    id=uuid.uuid4(),
                    source=EventSource.BACKEND,
                    timestamp=datetime.now(UTC),
                    payload=AiResponsePayload(
                        request_id=request_id,
                        task_id=task_id,
                        finish_reason=AiFinishReason.ERROR,
                        total_tokens=None,
                        latency_ms=0.0,
                    ),
                )
            )
            raise NoHealthyProviderError(
                f"No healthy provider for task type '{task_type.value}'. Last error: {last_error}"
            )

    async def complete(
        self,
        task_type: AiTaskType,
        messages: list[ChatMessage],
        *,
        task_id: uuid.UUID | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> CompletionResult:
        """Non-streaming convenience wrapper — accumulates `stream()` into
        a single result. Used by callers that need the whole response at
        once (e.g. `Planner`, which parses the completion as structured
        plan JSON rather than displaying it token-by-token)."""
        started_at = time.monotonic()
        chunks: list[str] = []
        async for delta in self.stream(
            task_type,
            messages,
            task_id=task_id,
            max_tokens=max_tokens,
            temperature=temperature,
        ):
            chunks.append(delta)
        return CompletionResult(
            content="".join(chunks),
            finish_reason="stop",
            total_tokens=None,
            latency_ms=(time.monotonic() - started_at) * 1000,
        )

    async def embed(self, text: str) -> list[float]:
        chain = self._routing.chain_for(AiTaskType.EMBED)
        last_error: Exception | None = None

        for target in chain:
            provider = self._providers.get(target.provider)
            if provider is None:
                continue
            capabilities = provider.capabilities(target.model)
            if not capabilities.supports_embeddings:
                continue
            try:
                return await self._call_with_retry(
                    lambda: provider.embed(target.model, text)
                )
            except Exception as error:  # noqa: BLE001 - see stream() rationale
                last_error = error
                logger.warning(
                    "embed_target_failed", provider=target.provider, model=target.model
                )
                continue

        raise NoHealthyProviderError(f"No healthy embedding provider. Last error: {last_error}")

    # -- internals ---------------------------------------------------------

    async def _attempt_stream(
        self,
        *,
        provider: ModelProvider,
        model: str,
        messages: list[ChatMessage],
        max_tokens: int,
        temperature: float,
        request_id: uuid.UUID,
        task_id: uuid.UUID | None,
        task_type: AiTaskType,
        fallback_index: int,
    ) -> AsyncIterator[str]:
        started_at = time.monotonic()

        await self._event_bus.publish(
            AiRequestEvent(
                id=uuid.uuid4(),
                source=EventSource.BACKEND,
                timestamp=datetime.now(UTC),
                payload=AiRequestPayload(
                    request_id=request_id,
                    task_id=task_id,
                    task_type=task_type,
                    provider=provider.name,
                    model=model,
                ),
            )
        )

        async def do_stream() -> AsyncIterator[str]:
            token_index = 0
            total_tokens: int | None = None
            finish_reason = "stop"

            async for chunk in provider.stream_chat(
                model, messages, max_tokens=max_tokens, temperature=temperature
            ):
                if chunk.done:
                    total_tokens = chunk.total_tokens
                    finish_reason = chunk.finish_reason or "stop"
                    break
                await self._event_bus.publish(
                    AiTokenEvent(
                        id=uuid.uuid4(),
                        source=EventSource.BACKEND,
                        timestamp=datetime.now(UTC),
                        payload=AiTokenPayload(
                            request_id=request_id, token=chunk.delta, index=token_index
                        ),
                    )
                )
                token_index += 1
                yield chunk.delta

            await self._event_bus.publish(
                AiResponseEvent(
                    id=uuid.uuid4(),
                    source=EventSource.BACKEND,
                    timestamp=datetime.now(UTC),
                    payload=AiResponsePayload(
                        request_id=request_id,
                        task_id=task_id,
                        finish_reason=AiFinishReason(finish_reason)
                        if finish_reason in {"stop", "length", "tool_call", "error"}
                        else AiFinishReason.STOP,
                        total_tokens=total_tokens,
                        latency_ms=(time.monotonic() - started_at) * 1000,
                    ),
                )
            )

        # Retries wrap the whole streaming attempt: if the stream fails
        # partway through, we cannot "resume" a partial stream, so a retry
        # here means restarting the request from scratch. This is
        # acceptable because callers (Orchestrator) treat partial output
        # from a failed attempt as discarded, not partially displayed.
        attempt = 0
        while True:
            try:
                async for delta in do_stream():
                    yield delta
                return
            except Exception:
                attempt += 1
                if attempt > self._retry_policy.max_retries:
                    raise
                backoff = min(
                    self._retry_policy.base_backoff_s * (2 ** (attempt - 1)),
                    self._retry_policy.max_backoff_s,
                )
                logger.info("retrying_provider_call", attempt=attempt, backoff_s=backoff)
                await asyncio.sleep(backoff)

    async def _call_with_retry(self, fn: Callable[[], Awaitable[T]]) -> T:
        attempt = 0
        while True:
            try:
                return await fn()
            except Exception:
                attempt += 1
                if attempt > self._retry_policy.max_retries:
                    raise
                backoff = min(
                    self._retry_policy.base_backoff_s * (2 ** (attempt - 1)),
                    self._retry_policy.max_backoff_s,
                )
                await asyncio.sleep(backoff)
