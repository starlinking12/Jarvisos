"""Security Center configuration. Same JSON-env-var pattern as
`voice/config.py`'s `VoiceSettings` — opt-in (`enabled: bool = False`),
sensible defaults, no env var required for the common case.
"""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import BaseModel, Field


class SecuritySettings(BaseModel):
    enabled: bool = False
    scan_interval_s: float = 300.0
    process_denylist: list[str] = Field(default_factory=list)
    watched_file_paths: list[str] = Field(default_factory=list)
    startup_known_entries: list[str] = Field(default_factory=list)
    scheduled_task_known_names: list[str] = Field(default_factory=list)
    network_allowed_listen_ports: list[int] = Field(default_factory=lambda: [8137])
    escalation_threshold: int = 3


def default_security_settings() -> SecuritySettings:
    return SecuritySettings()


@lru_cache
def get_security_settings(raw_json: str | None = None) -> SecuritySettings:
    if not raw_json:
        return default_security_settings()
    return SecuritySettings.model_validate(json.loads(raw_json))


__all__ = ["SecuritySettings", "default_security_settings", "get_security_settings"]
