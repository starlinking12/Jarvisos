from __future__ import annotations

import pytest

from jarvis_backend.ai import MockProvider, OllamaProvider
from jarvis_backend.config import ProviderConfig, Settings
from jarvis_backend.main import build_orchestrator, build_provider


def test_build_provider_constructs_ollama_provider_from_config() -> None:
    config = ProviderConfig(name="test-ollama", kind="ollama", host="http://127.0.0.1:11434")
    provider = build_provider(config)
    assert isinstance(provider, OllamaProvider)


def test_build_provider_constructs_mock_provider_from_config() -> None:
    config = ProviderConfig(name="test-mock", kind="mock")
    provider = build_provider(config)
    assert isinstance(provider, MockProvider)


def test_build_provider_rejects_unknown_kind() -> None:
    config = ProviderConfig(name="test-bad", kind="not-a-real-provider-kind")
    with pytest.raises(ValueError):
        build_provider(config)


def test_build_provider_ollama_requires_host() -> None:
    config = ProviderConfig(name="test-ollama-no-host", kind="ollama", host=None)
    with pytest.raises(ValueError):
        build_provider(config)


def test_build_orchestrator_wires_a_complete_stack() -> None:
    settings = Settings(
        JARVIS_PROVIDERS_JSON='[{"name": "mock", "kind": "mock"}]',
        JARVIS_ROUTING_JSON=(
            '{"rules": ['
            '{"task_type": "chat", "targets": [{"provider": "mock", "model": "mock-small"}]},'
            '{"task_type": "reasoning", "targets": [{"provider": "mock", "model": "mock-small"}]},'
            '{"task_type": "toolcall", "targets": [{"provider": "mock", "model": "mock-small"}]},'
            '{"task_type": "summarize", "targets": [{"provider": "mock", "model": "mock-small"}]},'
            '{"task_type": "embed", "targets": [{"provider": "mock", "model": "mock-small"}]}'
            "]}"
        ),
    )

    bundle = build_orchestrator(settings)

    assert "mock" in bundle.providers
    assert isinstance(bundle.providers["mock"], MockProvider)
    assert bundle.orchestrator is not None
    assert bundle.tool_registry is not None
    assert bundle.safety_gate is not None
