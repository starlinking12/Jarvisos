"""Runtime configuration for the JARVIS backend.

All configuration is environment-driven so the backend remains runnable
standalone (outside Electron) for development and testing, per ADR-0001.
Phase 2 extends this with typed provider/routing/retry/resource-limit
configuration for the ModelRouter and agent framework (see ADR-0002).

Complex structures (provider list, routing table) are configured via a
single JSON env var each rather than many flat env vars — this keeps the
shape of the config identical to how it's validated (a list of
`ProviderConfig`, a `RoutingConfig`), and avoids inventing an ad-hoc
flattened env-var naming scheme for nested data. Sensible built-in defaults
mean neither JSON var needs to be set for local development against a
default Ollama install.
"""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from jarvis_contracts import AiTaskType


class ProviderConfig(BaseModel):
    """Configuration for one instantiated model provider."""

    name: str
    kind: str
    host: str | None = None
    request_timeout_s: float = 120.0


class RoutingTarget(BaseModel):
    provider: str
    model: str


class RoutingRule(BaseModel):
    task_type: AiTaskType
    targets: list[RoutingTarget]

    @field_validator("targets")
    @classmethod
    def _non_empty(cls, value: list[RoutingTarget]) -> list[RoutingTarget]:
        if not value:
            raise ValueError("RoutingRule.targets must have at least one target")
        return value


class RoutingConfig(BaseModel):
    rules: list[RoutingRule]

    def chain_for(self, task_type: AiTaskType) -> list[RoutingTarget]:
        for rule in self.rules:
            if rule.task_type == task_type:
                return rule.targets
        raise KeyError(f"No routing rule configured for task type '{task_type.value}'")


class RetryPolicy(BaseModel):
    max_retries: int = 2
    base_backoff_s: float = 0.5
    max_backoff_s: float = 8.0


class ResourceLimits(BaseModel):
    max_concurrent_ai_requests: int = 4
    max_tokens_per_request: int = 4096
    max_concurrent_agent_tasks: int = 8


class PluginConfig(BaseModel):
    """Explicit allowlist for trusted local plugin code."""

    directories: tuple[str, ...] = ()
    allowed_ids: frozenset[str] = frozenset()


def _default_providers() -> list[ProviderConfig]:
    return [
        ProviderConfig(name="ollama-local", kind="ollama", host="http://127.0.0.1:11434"),
    ]


def _default_routing() -> RoutingConfig:
    return RoutingConfig(
        rules=[
            RoutingRule(
                task_type=AiTaskType.CHAT,
                targets=[
                    RoutingTarget(provider="ollama-local", model="qwen2.5"),
                    RoutingTarget(provider="ollama-local", model="deepseek-r1"),
                ],
            ),
            RoutingRule(
                task_type=AiTaskType.REASONING,
                targets=[
                    RoutingTarget(provider="ollama-local", model="deepseek-r1"),
                    RoutingTarget(provider="ollama-local", model="qwen2.5"),
                ],
            ),
            RoutingRule(task_type=AiTaskType.TOOLCALL, targets=[RoutingTarget(provider="ollama-local", model="qwen2.5")]),
            RoutingRule(task_type=AiTaskType.SUMMARIZE, targets=[RoutingTarget(provider="ollama-local", model="qwen2.5")]),
            RoutingRule(task_type=AiTaskType.EMBED, targets=[RoutingTarget(provider="ollama-local", model="qwen2.5")]),
        ]
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JARVIS_", extra="ignore")

    backend_port: int = Field(default=8137)
    log_level: str = Field(default="INFO")
    environment: str = Field(default="development")
    ollama_host: str = Field(default="http://127.0.0.1:11434")
    default_model: str = Field(default="qwen2.5")

    providers_json: str | None = Field(default=None, alias="JARVIS_PROVIDERS_JSON")
    routing_json: str | None = Field(default=None, alias="JARVIS_ROUTING_JSON")
    retry_policy_json: str | None = Field(default=None, alias="JARVIS_RETRY_POLICY_JSON")
    resource_limits_json: str | None = Field(default=None, alias="JARVIS_RESOURCE_LIMITS_JSON")
    voice_settings_json: str | None = Field(default=None, alias="JARVIS_VOICE_SETTINGS_JSON")
    security_settings_json: str | None = Field(
        default=None, alias="JARVIS_SECURITY_SETTINGS_JSON"
    )
    db_path: str | None = Field(default=None, alias="JARVIS_DB_PATH")
    automation_enabled: bool = Field(default=False, alias="JARVIS_AUTOMATION_ENABLED")
    # Phase 5: plugins are disabled unless both a directory and explicit
    # allowlist are configured. Discovery itself never imports plugin code.
    plugins_json: str | None = Field(default=None, alias="JARVIS_PLUGINS_JSON")

    def providers(self) -> list[ProviderConfig]:
        if not self.providers_json:
            return _default_providers()
        raw = json.loads(self.providers_json)
        return [ProviderConfig.model_validate(entry) for entry in raw]

    def routing(self) -> RoutingConfig:
        if not self.routing_json:
            return _default_routing()
        return RoutingConfig.model_validate_json(self.routing_json)

    def retry_policy(self) -> RetryPolicy:
        if not self.retry_policy_json:
            return RetryPolicy()
        return RetryPolicy.model_validate_json(self.retry_policy_json)

    def resource_limits(self) -> ResourceLimits:
        if not self.resource_limits_json:
            return ResourceLimits()
        return ResourceLimits.model_validate_json(self.resource_limits_json)

    def plugin_config(self) -> PluginConfig:
        if not self.plugins_json:
            return PluginConfig()
        return PluginConfig.model_validate_json(self.plugins_json)


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — import and call this, don't instantiate
    Settings() directly, so the whole process shares one config snapshot."""
    return Settings()
