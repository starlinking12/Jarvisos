from __future__ import annotations

from jarvis_backend.ai.mock_provider import MockProvider
from jarvis_backend.ai.warm_pool import WarmModelManager


class _WarmCountingProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.warm_calls: list[str] = []

    async def warm(self, model: str) -> None:
        self.warm_calls.append(model)


async def test_ensure_warm_warms_a_never_seen_model() -> None:
    provider = _WarmCountingProvider()
    manager = WarmModelManager(idle_reload_threshold_s=60.0)

    await manager.ensure_warm(provider, "mock-small")

    assert provider.warm_calls == ["mock-small"]


async def test_ensure_warm_skips_recently_used_model() -> None:
    provider = _WarmCountingProvider()
    manager = WarmModelManager(idle_reload_threshold_s=60.0)

    await manager.ensure_warm(provider, "mock-small")
    manager.touch(provider.name, "mock-small")
    await manager.ensure_warm(provider, "mock-small")

    # Only the first ensure_warm should have actually warmed — the second
    # call happened well within the idle threshold after touch().
    assert provider.warm_calls == ["mock-small"]


async def test_ensure_warm_rewarms_after_idle_threshold() -> None:
    provider = _WarmCountingProvider()
    manager = WarmModelManager(idle_reload_threshold_s=0.0)

    await manager.ensure_warm(provider, "mock-small")
    manager.touch(provider.name, "mock-small")
    await manager.ensure_warm(provider, "mock-small")

    # idle_reload_threshold_s=0 means every call after touch() is
    # considered stale immediately.
    assert provider.warm_calls == ["mock-small", "mock-small"]


async def test_warm_failure_does_not_raise() -> None:
    class _FailingWarmProvider(MockProvider):
        async def warm(self, model: str) -> None:
            raise RuntimeError("provider unreachable")

    provider = _FailingWarmProvider()
    manager = WarmModelManager()

    # Should not raise — warming is best-effort per warm_pool.py's docstring.
    await manager.ensure_warm(provider, "mock-small")
