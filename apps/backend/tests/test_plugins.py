from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis_backend.agents.tool_registry import ToolRegistry
from jarvis_backend.plugins.loader import PluginLoadError, PluginLoader
from jarvis_backend.plugins.types import PluginManifest


def _write_manifest(directory: Path, *, plugin_id: str = "example.plugin") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "jarvis.plugin.json"
    path.write_text(
        json.dumps(
            {
                "id": plugin_id,
                "version": "1.0.0",
                "name": "Example Plugin",
                "description": "test",
                "entry_point": "tests.test_plugins:plugin_factory",
                "requested_permissions": ["automation.input"],
            }
        ),
        encoding="utf-8",
    )
    return path


def plugin_factory(registry: ToolRegistry) -> None:
    """Test entry point proving that factories receive only the registry."""
    assert isinstance(registry, ToolRegistry)


def test_manifest_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        PluginManifest.model_validate(
            {
                "id": "example",
                "version": "1.0.0",
                "name": "Example",
                "entry_point": "tests.test_plugins:plugin_factory",
                "unexpected": True,
            }
        )


def test_discovery_is_metadata_only(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    loader = PluginLoader(directories=[tmp_path])

    discovered = loader.discover()

    assert list(discovered) == ["example.plugin"]
    assert discovered["example.plugin"].manifest.requested_permissions == ("automation.input",)


def test_unallowlisted_plugin_cannot_load(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    loader = PluginLoader(directories=[tmp_path])
    spec = loader.discover()["example.plugin"]

    with pytest.raises(PluginLoadError, match="not allowlisted"):
        loader.load(spec)


def test_allowlisted_plugin_factory_loads(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    loader = PluginLoader(directories=[tmp_path], allowed_ids=["example.plugin"])
    registry = ToolRegistry()

    loaded = loader.load_all(registry)

    assert loaded == ["example.plugin"]


def test_duplicate_plugin_ids_are_rejected(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_manifest(first)
    _write_manifest(second)

    with pytest.raises(PluginLoadError, match="Duplicate plugin id"):
        PluginLoader(directories=[tmp_path]).discover()
