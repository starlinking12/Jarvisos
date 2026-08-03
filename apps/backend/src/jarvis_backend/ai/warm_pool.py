"""Warm model management.

Local model runtimes (Ollama in particular) pay a real cost — often
seconds — to load a model into GPU/CPU memory on first use, and evict it
after an idle period. `WarmModelManager` tracks per-model last-use time and
proactively re-issues a lightweight "warm" call after an idle threshold, so
the *next* real user-facing request doesn't stall on a cold load. This is
purely a latency optimization layer sitting in front of `ModelProvider.warm`
— it holds no model weights or provider state itself, keeping it trivially
replaceable per the "every subsystem must be replaceable" principle.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import structlog

from .types import ModelProvider

logger = structlog.get_logger("jarvis_backend.ai.warm_pool")


@dataclass(slots=True)
class _WarmEntry:
    provider_name: str
    last_used_at: float


class WarmModelManager:
    """Tracks warm state for (provider, model) pairs. Call `touch()` after
    every real completion; call `ensure_warm()` before a request that can
    tolerate a small extra async call if it means avoiding cold-load
    latency on the actual request that follows (e.g. speculative pre-warm
    when a user starts typing — not wired to a UI trigger until a later
    phase, but the mechanism is real and usable today).
    """

    def __init__(self, idle_reload_threshold_s: float = 300.0) -> None:
        self._idle_reload_threshold_s = idle_reload_threshold_s
        self._entries: dict[tuple[str, str], _WarmEntry] = {}
        self._lock = asyncio.Lock()

    def touch(self, provider_name: str, model: str) -> None:
        """Record that (provider, model) was just used for a real request."""
        self._entries[(provider_name, model)] = _WarmEntry(
            provider_name=provider_name, last_used_at=time.monotonic()
        )

    async def ensure_warm(self, provider: ModelProvider, model: str) -> None:
        """Warms `model` on `provider` if it hasn't been used recently
        enough to be considered still-loaded. Safe to call before every
        request — it is a no-op for models used within the idle threshold."""
        key = (provider.name, model)
        async with self._lock:
            entry = self._entries.get(key)
            now = time.monotonic()
            is_stale = entry is None or (now - entry.last_used_at) > self._idle_reload_threshold_s

            if not is_stale:
                return

            self._entries[key] = _WarmEntry(provider_name=provider.name, last_used_at=now)

        logger.info("warming_model", provider=provider.name, model=model)
        try:
            await provider.warm(model)
        except Exception:  # noqa: BLE001 - warming is best-effort; the real
            # request that follows will surface any genuine provider failure
            # with a proper error path, so a warm-up failure alone should
            # not block or crash the caller.
            logger.warning("warm_failed", provider=provider.name, model=model, exc_info=True)

    def known_models(self) -> list[str]:
        return sorted({model for (_provider, model) in self._entries})
