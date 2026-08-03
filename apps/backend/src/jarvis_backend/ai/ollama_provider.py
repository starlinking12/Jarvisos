"""Ollama provider — talks to a local Ollama server's HTTP API.

Ollama's `/api/chat` endpoint returns newline-delimited JSON objects when
`stream: true`, one per generated token/chunk, terminated by an object with
`"done": true`. This provider translates that wire format into the
provider-agnostic `StreamChunk`/`ChatMessage` vocabulary from `ai.types`,
so nothing above this module ever sees an Ollama-specific shape.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

import httpx
import structlog

from .types import ChatMessage, ModelCapabilities, ProviderHealth, StreamChunk

logger = structlog.get_logger("jarvis_backend.ai.ollama_provider")

# Conservative defaults for models this project's ADR-0002 targets
# (Qwen2.5, DeepSeek). Ollama does not report context length over the
# `/api/chat` wire, so this is configured per-model rather than queried —
# override via OllamaProvider(context_windows={...}) for models not listed
# here.
DEFAULT_CONTEXT_WINDOWS: dict[str, int] = {
    "qwen2.5": 32_768,
    "deepseek-r1": 32_768,
    "deepseek-coder-v2": 16_384,
}
FALLBACK_CONTEXT_WINDOW = 8192


class OllamaProvider:
    """Implements the `ModelProvider` protocol (`ai/types.py`) against a
    local Ollama instance. Structural typing means this class needs no base
    class import — it satisfies the protocol by shape alone."""

    name = "ollama"

    def __init__(
        self,
        host: str,
        *,
        context_windows: dict[str, int] | None = None,
        request_timeout_s: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self._context_windows = {**DEFAULT_CONTEXT_WINDOWS, **(context_windows or {})}
        self._client = client or httpx.AsyncClient(base_url=self._host, timeout=request_timeout_s)

    async def health_check(self) -> ProviderHealth:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            models = [entry["name"] for entry in data.get("models", [])]
            return ProviderHealth(healthy=True, detail="reachable", available_models=models)
        except httpx.HTTPError as error:
            return ProviderHealth(healthy=False, detail=f"unreachable: {error}")

    def capabilities(self, model: str) -> ModelCapabilities:
        base_model = model.split(":", 1)[0]
        max_context = self._context_windows.get(base_model, FALLBACK_CONTEXT_WINDOW)
        return ModelCapabilities(
            supports_streaming=True,
            supports_tool_calls=True,
            supports_embeddings=True,
            max_context_tokens=max_context,
        )

    async def stream_chat(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        payload = {
            "model": model,
            "stream": True,
            "messages": [
                {"role": message.role.value, "content": message.content} for message in messages
            ],
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        index = 0
        started_at = time.monotonic()

        async with self._client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)

                if chunk.get("done"):
                    yield StreamChunk(
                        delta="",
                        index=index,
                        done=True,
                        finish_reason=chunk.get("done_reason", "stop"),
                        total_tokens=chunk.get("eval_count"),
                    )
                    logger.debug(
                        "ollama_stream_complete",
                        model=model,
                        latency_ms=(time.monotonic() - started_at) * 1000,
                    )
                    return

                delta = chunk.get("message", {}).get("content", "")
                if delta:
                    yield StreamChunk(delta=delta, index=index, done=False)
                    index += 1

    async def embed(self, model: str, text: str) -> list[float]:
        response = await self._client.post(
            "/api/embeddings", json={"model": model, "prompt": text}
        )
        response.raise_for_status()
        data = response.json()
        embedding = data.get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError(f"Ollama returned no embedding for model '{model}'")
        return embedding

    async def warm(self, model: str) -> None:
        # An empty-message chat request with stream disabled loads the
        # model into memory without generating meaningful output — Ollama's
        # documented pattern for pre-warming.
        await self._client.post(
            "/api/chat",
            json={"model": model, "messages": [], "stream": False},
        )

    async def aclose(self) -> None:
        await self._client.aclose()
