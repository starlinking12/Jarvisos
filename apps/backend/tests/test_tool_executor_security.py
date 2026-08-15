from __future__ import annotations

import uuid

import pytest

from jarvis_contracts import EventSource

from jarvis_backend.agents.safety_gate import (
    PermissionDecisionKind,
    PermissionScope,
    SafetyGate,
    SafetyPolicy,
)
from jarvis_backend.agents.task_ledger import TaskLedger
from jarvis_backend.agents.tool_executor import ToolExecutor
from jarvis_backend.agents.tool_registry import ToolRegistry, ToolSpec
from jarvis_backend.agents.types import PlanStep
from jarvis_backend.event_bus import EventBus


@pytest.mark.asyncio
async def test_owner_agent_is_enforced_at_tool_executor() -> None:
    registry = ToolRegistry()
    invoked = False

    async def handler(_args: dict[str, object]) -> str:
        nonlocal invoked
        invoked = True
        return "should not run"

    registry.register(
        ToolSpec(
            name="automation.test",
            description="test",
            handler=handler,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )

    task_ledger = TaskLedger()
    task = task_ledger.create_task(
        goal="security test",
        requested_by=EventSource.ORCHESTRATOR,
    )
    executor = ToolExecutor(
        registry=registry,
        safety_gate=SafetyGate(SafetyPolicy.production_default()),
        task_ledger=task_ledger,
        event_bus=EventBus(),
    )

    observation = await executor.execute(
        task.task_id,
        PlanStep(
            step_id=uuid.uuid4(),
            description="attempt wrong owner",
            agent=EventSource.AGENT_DEVELOPER,
            tool="automation.test",
        ),
    )

    assert observation.success is False
    assert "restricted to agent" in observation.detail
    assert invoked is False


@pytest.mark.asyncio
async def test_prompt_scope_denies_without_approval_broker() -> None:
    policy = SafetyPolicy.production_default()
    policy.overrides[PermissionScope.AUTOMATION_INPUT] = PermissionDecisionKind.PROMPT
    gate = SafetyGate(policy)

    result = await gate.check(
        PermissionScope.AUTOMATION_INPUT,
        reason="test automation",
        requested_by=EventSource.AGENT_AUTOMATION,
        task_id=str(uuid.uuid4()),
    )

    assert result.granted is False
    assert result.decision is PermissionDecisionKind.DENY
