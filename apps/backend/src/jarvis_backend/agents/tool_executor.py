"""ToolExecutor — the single tool execution and authorization choke point."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from jarvis_contracts import AgentObserveEvent, AgentObservePayload, EventSource

from jarvis_backend.event_bus import EventBus

from .safety_gate import PermissionScope, SafetyGate
from .task_ledger import TaskLedger
from .tool_registry import ToolRegistry
from .types import Observation, PlanStep

logger = structlog.get_logger("jarvis_backend.agents.tool_executor")


class ToolExecutor:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        safety_gate: SafetyGate,
        task_ledger: TaskLedger,
        event_bus: EventBus,
    ) -> None:
        self._registry = registry
        self._safety_gate = safety_gate
        self._task_ledger = task_ledger
        self._event_bus = event_bus

    async def execute(self, task_id: uuid.UUID, step: PlanStep) -> Observation:
        if step.tool is None:
            observation = Observation(
                step_id=step.step_id,
                success=False,
                detail="Step has no associated tool for ToolExecutor to run.",
            )
            await self._publish_and_record(task_id, observation)
            return observation

        spec = self._registry.get(step.tool)
        if spec is None:
            observation = Observation(
                step_id=step.step_id,
                success=False,
                detail=f"Unknown tool '{step.tool}'.",
            )
            await self._publish_and_record(task_id, observation)
            return observation

        # Bind execution to the task's planned step once planning exists. This
        # prevents a caller from reusing a valid task id while swapping in a
        # different agent, tool, arguments, or step description.
        if not self._task_ledger.is_planned_step_authorized(task_id, step):
            observation = Observation(
                step_id=step.step_id,
                success=False,
                detail="Tool execution denied: step does not match the task plan.",
            )
            await self._publish_and_record(task_id, observation)
            return observation

        # Defense-in-depth for callers that reach ToolExecutor without first
        # passing through DomainAgent's allowlist check. A tool declaring an
        # owner may only be executed by that exact agent identity.
        if spec.owner_agent is not None and spec.owner_agent != step.agent:
            observation = Observation(
                step_id=step.step_id,
                success=False,
                detail=(
                    f"Tool '{spec.name}' is restricted to agent "
                    f"'{spec.owner_agent.value}'."
                ),
            )
            await self._publish_and_record(task_id, observation)
            return observation

        if spec.permission_scope is not None:
            try:
                scope = PermissionScope(spec.permission_scope)
            except ValueError:
                logger.error("invalid_tool_permission_scope", tool=spec.name)
                observation = Observation(
                    step_id=step.step_id,
                    success=False,
                    detail=(
                        f"Permission denied: tool '{spec.name}' declares an invalid "
                        f"permission scope."
                    ),
                )
                await self._publish_and_record(task_id, observation)
                return observation

            check = await self._safety_gate.check(
                scope,
                reason=f"Tool '{spec.name}' requested by step: {step.description}",
                requested_by=step.agent,
                task_id=str(task_id),
            )
            if not check.granted:
                observation = Observation(
                    step_id=step.step_id,
                    success=False,
                    detail=f"Permission denied for scope '{spec.permission_scope}'.",
                )
                await self._publish_and_record(task_id, observation)
                return observation

        try:
            result_text = await spec.handler(step.tool_args)
            observation = Observation(step_id=step.step_id, success=True, detail=result_text)
        except Exception as error:  # noqa: BLE001 - tool failures become observations
            logger.warning("tool_execution_failed", tool=step.tool, error=str(error))
            observation = Observation(
                step_id=step.step_id, success=False, detail=f"Tool error: {error}"
            )

        await self._publish_and_record(task_id, observation)
        return observation

    async def _publish_and_record(self, task_id: uuid.UUID, observation: Observation) -> None:
        self._task_ledger.record_observation(task_id, observation)
        await self._event_bus.publish(
            AgentObserveEvent(
                id=uuid.uuid4(),
                source=EventSource.ORCHESTRATOR,
                timestamp=datetime.now(UTC),
                payload=AgentObservePayload(
                    task_id=task_id,
                    step_id=observation.step_id,
                    observation=observation.detail,
                    success=observation.success,
                ),
            )
        )
