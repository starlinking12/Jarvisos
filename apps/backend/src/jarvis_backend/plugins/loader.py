"""Safe, explicit plugin discovery and loading boundary.

A manifest can be discovered without importing plugin code. Loading requires
both an explicit allowlist entry and a valid ``module:attribute`` entry point.
The loader does not grant permissions or bypass ToolExecutor/SafetyGate.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .types import PluginManifest, PluginSpec


class PluginLoadError(RuntimeError):
    """Raised when a plugin cannot be safely discovered or loaded."""


class PluginLoader:
    """Discover manifests and load only explicitly allowlisted plugins."""

    MANIFEST_NAME = "jarvis.plugin.json"

    def __init__(self, *, directories: Iterable[Path], allowed_ids: Iterable[str] = ()) -> None:
        self._directories = tuple(Path(directory) for directory in directories)
        self._allowed_ids = frozenset(allowed_ids)

    def discover(self) -> dict[str, PluginSpec]:
        """Return valid manifests keyed by plugin id; never imports code."""
        discovered: dict[str, PluginSpec] = {}
        for directory in self._directories:
            if not directory.exists():
                continue
            for manifest_path in sorted(directory.rglob(self.MANIFEST_NAME)):
                spec = self._read_manifest(manifest_path)
                if spec.plugin_id in discovered:
                    raise PluginLoadError(f"Duplicate plugin id '{spec.plugin_id}'")
                discovered[spec.plugin_id] = spec
        return discovered

    def load(self, spec: PluginSpec) -> Callable[..., Any]:
        """Import an allowlisted plugin entry point.

        Importing third-party code is intentionally gated by plugin id. The
        returned factory is not invoked here; composition code decides how to
        provide the registry/context and still routes resulting tools through
        the normal authorization choke point.
        """
        if spec.plugin_id not in self._allowed_ids:
            raise PluginLoadError(f"Plugin '{spec.plugin_id}' is not allowlisted")

        module_name, separator, attribute = spec.manifest.entry_point.partition(":")
        if not separator or not module_name or not attribute:
            raise PluginLoadError(
                f"Plugin '{spec.plugin_id}' has invalid entry point "
                f"'{spec.manifest.entry_point}'; expected module:attribute"
            )

        try:
            module = importlib.import_module(module_name)
            factory = getattr(module, attribute)
        except (ImportError, AttributeError) as exc:
            raise PluginLoadError(
                f"Failed to load plugin '{spec.plugin_id}': {exc}"
            ) from exc

        if not callable(factory):
            raise PluginLoadError(
                f"Plugin '{spec.plugin_id}' entry point '{spec.manifest.entry_point}' is not callable"
            )
        return factory

    @staticmethod
    def _read_manifest(path: Path) -> PluginSpec:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            manifest = PluginManifest.model_validate(raw)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise PluginLoadError(f"Invalid plugin manifest '{path}': {exc}") from exc
        return PluginSpec(manifest=manifest, manifest_path=str(path))
