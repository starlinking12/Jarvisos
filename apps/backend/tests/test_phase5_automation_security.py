from __future__ import annotations

from jarvis_backend.agents.safety_gate import PermissionDecisionKind, PermissionScope, SafetyPolicy
from jarvis_backend.config import Settings


def test_automation_is_disabled_by_default() -> None:
    assert Settings().automation_enabled is False


def test_automation_scope_is_available_for_prompt_policy() -> None:
    policy = SafetyPolicy.production_default()
    policy.overrides[PermissionScope.AUTOMATION_INPUT] = PermissionDecisionKind.PROMPT

    assert policy.overrides[PermissionScope.AUTOMATION_INPUT] == PermissionDecisionKind.PROMPT
    assert policy.default == PermissionDecisionKind.DENY
