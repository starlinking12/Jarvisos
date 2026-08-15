from __future__ import annotations

import uuid

from jarvis_contracts import EventSource

from jarvis_backend.agents.safety_gate import PermissionDecisionKind, SafetyGate, SafetyPolicy
from jarvis_backend.agents.task_ledger import TaskLedger
from jarvis_backend.agents.tool_executor import ToolExecutor
from jarvis_backend.agents.tool_registry import ToolRegistry, ToolSpec
from jarvis_backend.agents.types import PlanStep
from jarvis_backend.event_bus import EventBus


def _make_executor(registry: ToolRegistry, *, allow_all: bool = False) -> tuple[ToolExecutor, TaskLedger]:
    policy = SafetyPolicy(
        default=PermissionDecisionKind.ALLOW if allow_all else PermissionDecisionKind.DENY
    )
    task_ledger = TaskLedger()
    return (
        ToolExecutor(
            registry=registry,
            safety_gate=SafetyGate(policy),
            task_ledger=task_ledger,
            event_bus=EventBus(),
        ),
        task_ledger,
    )


async def test_execute_runs_tool_with_no_permission_scope() -> None:
    async def handler(args: dict[str, object]) -> str:
        return "success"

    registry = ToolRegistry()
    registry.register(ToolSpec(name="free.tool", description="no scope", handler=handler))
    executor, task_ledger = _make_executor(registry)
    task = task_ledger.create_task(goal="tool test", requested_by=EventSource.ORCHESTRATOR)

    step = PlanStep(
        step_id=uuid.uuid4(),
        description="run it",
        agent=EventSource.AGENT_DEVELOPER,
        tool="free.tool",
    )

    observation = await executor.execute(task.task_id, step)

    assert observation.success is True
    assert observation.detail == "success"


async def test_execute_denies_gated_tool_by_default_policy() -> None:
    async def handler(args: dict[str, object]) -> str:
        return "should not run"

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="gated.tool",
            description="needs permission",
            handler=handler,
            permission_scope="filesystem.write",
        )
    )
    executor, task_ledger = _make_executor(registry, allow_all=False)
    task = task_ledger.create_task(goal="gated tool test", requested_by=EventSource.ORCHESTRATOR)

    step = PlanStep(
        step_id=uuid.uuid4(),
        description="write a file",
        agent=EventSource.AGENT_DEVELOPER,
        tool="gated.tool",
    )

    observation = await executor.execute(task.task_id, step)

    assert observation.success is False
    assert "Permission denied" in observation.detail


async def test_execute_allows_gated_tool_when_policy_grants_it() -> None:
    async def handler(args: dict[str, object]) -> str:
        return "wrote the file"

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="gated.tool",
            description="needs permission",
            handler=handler,
            permission_scope="filesystem.write",
        )
    )
    executor, task_ledger = _make_executor(registry, allow_all=True)
    task = task_ledger.create_task(goal="allowed tool test", requested_by=EventSource.ORCHESTRATOR)

    step = PlanStep(
        step_id=uuid.uuid4(),
        description="write a file",
        agent=EventSource.AGENT_DEVELOPER,
        tool="gated.tool",
    )

    observation = await executor.execute(task.task_id, step)

    assert observation.success is True
    assert observation.detail == "wrote the file"


async def test_execute_reports_unknown_tool_as_failed_observation() -> None:
    executor, task_ledger = _make_executor(ToolRegistry())
    task = task_ledger.create_task(goal="unknown tool test", requested_by=EventSource.ORCHESTRATOR)
    step = PlanStep(
        step_id=uuid.uuid4(),
        description="run nonexistent tool",
        agent=EventSource.AGENT_DEVELOPER,
        tool="does.not.exist",
    )

    observation = await executor.execute(task.task_id, step)

    assert observation.success is False
    assert "Unknown tool" in observation.detail


async def test_execute_catches_handler_exceptions() -> None:
    async def failing_handler(args: dict[str, object]) -> str:
        raise RuntimeError("handler blew up")

    registry = ToolRegistry()
    registry.register(ToolSpec(name="broken.tool", description="fails", handler=failing_handler))
    executor, task_ledger = _make_executor(registry)
    task = task_ledger.create_task(goal="broken tool test", requested_by=EventSource.ORCHESTRATOR)

    step = PlanStep(
        step_id=uuid.uuid4(),
        description="run broken tool",
        agent=EventSource.AGENT_DEVELOPER,
        tool="broken.tool",
    )

    observation = await executor.execute(task.task_id, step)

    assert observation.success is False
    assert "Tool error" in observation.detail


async def test_execute_reports_missing_tool_reference() -> None:
    executor, task_ledger = _make_executor(ToolRegistry())
    task = task_ledger.create_task(goal="missing tool test", requested_by=EventSource.ORCHESTRATOR)
    step = PlanStep(
        step_id=uuid.uuid4(),
        description="no tool set",
        agent=EventSource.AGENT_DEVELOPER,
        tool=None,
    )

    observation = await executor.execute(task.task_id, step)

    assert observation.success is False
