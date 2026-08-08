"""Typed plugin manifest contracts for Phase 5.

The manifest is deliberately small: identity, version, description, Python
entry point, and permissions requested by the plugin. Tool authorization still
belongs to ToolExecutor/SafetyGate; a plugin manifest never grants permission.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PluginManifest(BaseModel):
    """On-disk metadata describing one trusted JARVIS plugin."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    version: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1000)
    entry_point: str = Field(min_length=3, max_length=255)
    requested_permissions: tuple[str, ...] = ()

    @field_validator("requested_permissions")
    @classmethod
    def _unique_permissions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("requested_permissions must not contain duplicates")
        return value


class PluginSpec(BaseModel):
    """Runtime plugin record after manifest discovery."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: PluginManifest
    manifest_path: str

    @property
    def plugin_id(self) -> str:
        return self.manifest.id
