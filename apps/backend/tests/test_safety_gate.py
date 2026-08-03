from __future__ import annotations

from jarvis_contracts import EventSource

from jarvis_backend.agents.safety_gate import (
    PermissionDecisionKind,
    PermissionScope,
    SafetyGate,
    SafetyPolicy,
)


async def test_production_default_denies_everything_by_default() -> None:
    gate = SafetyGate(SafetyPolicy.production_default())

    result = await gate.check(
        PermissionScope.FILESYSTEM_WRITE,
        reason="test",
        requested_by=EventSource.AGENT_DEVELOPER,
        task_id="task-1",
    )

    assert result.granted is False
    assert result.decision == PermissionDecisionKind.DENY


async def test_explicit_allow_override_grants_permission() -> None:
    policy = SafetyPolicy(
        default=PermissionDecisionKind.DENY,
        overrides={PermissionScope.NETWORK_EGRESS: PermissionDecisionKind.ALLOW},
    )
    gate = SafetyGate(policy)

    result = await gate.check(
        PermissionScope.NETWORK_EGRESS,
        reason="test",
        requested_by=EventSource.AGENT_RESEARCH,
        task_id="task-2",
    )

    assert result.granted is True
    assert result.decision == PermissionDecisionKind.ALLOW


async def test_prompt_tier_resolves_to_deny_in_phase_2() -> None:
    # No interactive approval channel exists yet from backend to the
    # Electron permission dialog — see safety_gate.py's module docstring.
    policy = SafetyPolicy(
        default=PermissionDecisionKind.DENY,
        overrides={PermissionScope.AUTOMATION_INPUT: PermissionDecisionKind.PROMPT},
    )
    gate = SafetyGate(policy)

    result = await gate.check(
        PermissionScope.AUTOMATION_INPUT,
        reason="test",
        requested_by=EventSource.AGENT_AUTOMATION,
        task_id="task-3",
    )

    assert result.granted is False


async def test_scopes_not_in_overrides_use_policy_default() -> None:
    policy = SafetyPolicy(
        default=PermissionDecisionKind.ALLOW,
        overrides={PermissionScope.SHELL_EXECUTE: PermissionDecisionKind.DENY},
    )
    gate = SafetyGate(policy)

    allowed = await gate.check(
        PermissionScope.PROCESS_CONTROL,
        reason="uses default",
        requested_by=EventSource.AGENT_DEVELOPER,
        task_id="task-4",
    )
    denied = await gate.check(
        PermissionScope.SHELL_EXECUTE,
        reason="explicit override",
        requested_by=EventSource.AGENT_DEVELOPER,
        task_id="task-4",
    )

    assert allowed.granted is True
    assert denied.granted is False
