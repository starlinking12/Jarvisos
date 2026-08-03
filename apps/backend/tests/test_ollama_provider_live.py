"""Live Ollama validation.

These tests talk to a real, locally-running Ollama server if one is
reachable, and are skipped automatically (not via an opt-in flag the
developer has to remember) when it isn't — CI and most local dev
environments won't have Ollama running, and that must never fail the
suite. Set `JARVIS_OLLAMA_TEST_HOST` to point at a non-default host; the
default matches `OllamaProvider`'s own default (`http://127.0.0.1:11434`).
"""

from __future__ import annotations

import os

import httpx
import pytest

from jarvis_backend.ai.ollama_provider import OllamaProvider
from jarvis_backend.ai.types import ChatMessage, ChatRole

OLLAMA_HOST = os.environ.get("JARVIS_OLLAMA_TEST_HOST", "http://127.0.0.1:11434")


async def _ollama_is_reachable() -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            response = await client.get(f"{OLLAMA_HOST}/api/tags")
            return response.status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture
async def require_live_ollama() -> None:
    if not await _ollama_is_reachable():
        pytest.skip(
            f"No reachable Ollama server at {OLLAMA_HOST} — skipping live validation. "
            "Start Ollama locally to run this test."
        )


@pytest.mark.live_ollama
async def test_ollama_health_check_reports_reachable(require_live_ollama: None) -> None:
    provider = OllamaProvider(OLLAMA_HOST)
    health = await provider.health_check()
    assert health.healthy is True
    await provider.aclose()


@pytest.mark.live_ollama
async def test_ollama_streams_a_real_completion(require_live_ollama: None) -> None:
    provider = OllamaProvider(OLLAMA_HOST)
    health = await provider.health_check()
    if not health.available_models:
        pytest.skip("Ollama is reachable but has no models pulled — cannot validate completion.")

    model = health.available_models[0]
    chunks = []
    async for chunk in provider.stream_chat(
        model,
        [ChatMessage(role=ChatRole.USER, content="Reply with the single word: OK")],
        max_tokens=16,
    ):
        chunks.append(chunk)

    assert len(chunks) > 0
    assert chunks[-1].done is True
    await provider.aclose()


@pytest.mark.live_ollama
async def test_ollama_capabilities_reports_positive_context_window(
    require_live_ollama: None,
) -> None:
    provider = OllamaProvider(OLLAMA_HOST)
    caps = provider.capabilities("qwen2.5")
    assert caps.max_context_tokens > 0
    assert caps.supports_streaming is True
    await provider.aclose()
