"""Phase 5 plugin discovery and loading primitives.

Plugins are trusted local extensions. Discovery is metadata-only; execution is
opt-in through an explicit allowlist in Settings so merely placing a manifest
on disk cannot execute code.
"""

from .loader import PluginLoader, PluginLoadError
from .types import PluginManifest, PluginSpec

__all__ = ["PluginLoader", "PluginLoadError", "PluginManifest", "PluginSpec"]
