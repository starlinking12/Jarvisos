"""Orchestrator — the top tier of the three-tier hierarchy (ADR-0008).

Per the project mandate: "Only the Orchestrator communicates with the
user. All other agents operate internally." Concretely, this means the
Orchestrator is the only component in the entire backend that publishes
`orchestrator.message` events — domain agents and tools never do, even
though their `agent.step`/`agent.observe` events are visible on the event
bus for HUD debug widgets to display as internal telemetry (not as chat).

Full lifecycle per user message, each stage publishing its corresponding
event (see ADR-0003 for the event sequence rationale):

  1. `agent.task.created` — a new task is opened in the TaskLedger.
  2. `agent.plan` — the Planner decomposes the goal into steps.
  3. `agent.step` (per step, status=running) → the assigned DomainAgent
     runs it → `agent.observe` (published by ToolExecutor or here, for
     reasoning-only steps).
  4. `orchestrator.message` (streamed deltas) — the actual user-visible
     response, composed from the plan's observations.
  5. `agent.complete` (or `agent.error` if the task failed outright).

Correlation: every event in one task's lifecycle carries that task's
`task_id`, and `structlog`'s contextvars bind `correlation_id=str(task_id)`
for the duration of `handle_user_message`, so backend logs for one user
request can be filtered to exactly that request regardless of which
module emitted them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from jarvis_contracts import (
    AgentCompleteEvent,
    AgentCompletePayload,
    AgentErrorEvent,
    AgentErrorPayload,
    AgentObserveEvent,
    AgentObservePayload,
    AgentPlanEvent,
    AgentPlanPayload,
    AgentStepEvent,
    AgentStepPayload,
    AgentTaskCreatedEvent,
    AgentTaskCreatedPayload,
    AiTaskType,
    EventSource,
    MessageRole,
    OrchestratorMessageEvent,
    OrchestratorMessagePayload,
    PlanStepSchema,
    TaskStatus,
)

from jarvis_backend.ai import ChatMessage, ChatRole, ModelRouter
from jarvis_backend.event_bus import EventBus
from jarvis_backend.memory import RetrievalPipeline

from .domain_agent import DomainAgent
from .planner import Planner
from .task_ledger import TaskLedger
from .types import Plan, PlanStep

logger = structlog.get_logger("jarvis_backend.agents.orchestrator")

_ORCHESTRATOR_SYSTEM_PROMPT = (
    "You are JARVIS, a local-first AI operating environment. You have just "
    "coordinated internal agents to investigate the user's request; their "
    "findings are summarized below as context. Respond to the user directly, "
    "concisely, and helpfully, in your own words — do not describe your "
    "internal process unless asked."
)


class Orchestrator:
    def __init__(
        self,
        *,
        model_router: ModelRouter,
        planner: Planner,
        task_ledger: TaskLedger,
        memory: RetrievalPipeline,
        event_bus: EventBus,
        agents: dict[EventSource, DomainAgent],
    ) -> None:
        self._model_router = model_router
        self._planner = planner
        self._task_ledger = task_ledger
        self._memory = memory
        self._event_bus = event_bus
        self._agents = agents

    async def handle_user_message(self, conversation_id: uuid.UUID, text: str) -> str:
        """Runs the full plan → execute → respond lifecycle for one user
        message and returns the final assembled response text (the caller,
        `api/routes_ai.py`, uses the streamed `orchestrator.message` events
        as the real-time channel; the return value is for callers that
        need the final text synchronously, e.g. tests)."""

        task = self._task_ledger.create_task(goal=text, requested_by=EventSource.ORCHESTRATOR)
        task_id = task.task_id

        with structlog.contextvars.bound_contextvars(correlation_id=str(task_id)):
            await self._event_bus.publish(
                AgentTaskCreatedEvent(
                    id=uuid.uuid4(),
                    source=EventSource.ORCHESTRATOR,
                    timestamp=datetime.now(UTC),
                    payload=AgentTaskCreatedPayload(
                        task_id=task_id, goal=text, requested_by=EventSource.ORCHESTRATOR
                    ),
                )
            )

            self._memory.working_memory.append(
                conversation_id, ChatMessage(role=ChatRole.USER, content=text)
            )

            try:
                plan = await self._planner.plan(
                    goal=text, task_id=task_id, available_agents=list(self._agents.keys())
                )
            except Exception as error:  # noqa: BLE001 - planning failure must degrade
                logger.warning("planning_failed_falling_back", error=str(error))
                await self._event_bus.publish(
                    AgentErrorEvent(
                        id=uuid.uuid4(),
                        source=EventSource.ORCHESTRATOR,
                        timestamp=datetime.now(UTC),
                        payload=AgentErrorPayload(
                            task_id=task_id,
                            step_id=None,
                            message=f"Planning failed, falling back to direct response: {error}",
                            recoverable=True,
                        ),
                    )
                )
                plan = Plan(
                    task_id=task_id,
                    goal=text,
                    steps=[],
                )

            self._task_ledger.set_plan(task_id, plan)
            await self._publish_plan(task_id, plan)

            for step in plan.steps:
                if step.agent == EventSource.ORCHESTRATOR:
                    # A step explicitly assigned to the Orchestrator means
                    # "just respond directly" — no domain agent dispatch
                    # needed; the response synthesis step below already
                    # covers this, so we skip dispatch but still record the
                    # step's lifecycle for a complete audit trail.
                    await self._publish_step(task_id, step, TaskStatus.COMPLETED)
                    continue

                await self._publish_step(task_id, step, TaskStatus.RUNNING)
                agent = self._agents.get(step.agent)
                if agent is None:
                    logger.warning("no_agent_for_step", agent=step.agent.value)
                    await self._event_bus.publish(
                        AgentErrorEvent(
                            id=uuid.uuid4(),
                            source=EventSource.ORCHESTRATOR,
                            timestamp=datetime.now(UTC),
                            payload=AgentErrorPayload(
                                task_id=task_id,
                                step_id=step.step_id,
                                message=f"No domain agent registered for '{step.agent.value}'.",
                                recoverable=True,
                            ),
                        )
                    )
                    await self._publish_step(task_id, step, TaskStatus.FAILED)
                    continue

                observation = await agent.handle_step(task_id, step)
                # ToolExecutor owns persistence/event publication for tool
                # observations. Reasoning-only observations have no executor
                # in their path, so the Orchestrator must record and publish
                # them here; otherwise their findings disappear before
                # response synthesis and the TaskLedger is incomplete.
                if step.tool is None:
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
                await self._publish_step(task_id, step, TaskStatus.COMPLETED)

            try:
                response_text = await self._synthesize_response(task_id, conversation_id, plan)
            except Exception as error:  # noqa: BLE001 - a total AI-call failure must still
                # resolve the task (as failed) and notify the HUD, not crash the request handler.
                logger.error("response_synthesis_failed", error=str(error))
                await self._event_bus.publish(
                    AgentErrorEvent(
                        id=uuid.uuid4(),
                        source=EventSource.ORCHESTRATOR,
                        timestamp=datetime.now(UTC),
                        payload=AgentErrorPayload(
                            task_id=task_id,
                            step_id=None,
                            message=f"Failed to generate a response: {error}",
                            recoverable=False,
                        ),
                    )
                )
                self._task_ledger.complete_task(
                    task_id, summary="Failed to generate a response.", success=False
                )
                await self._event_bus.publish(
                    AgentCompleteEvent(
                        id=uuid.uuid4(),
                        source=EventSource.ORCHESTRATOR,
                        timestamp=datetime.now(UTC),
                        payload=AgentCompletePayload(
                            task_id=task_id,
                            summary="Failed to generate a response.",
                            success=False,
                        ),
                    )
                )
                raise

            self._memory.working_memory.append(
                conversation_id, ChatMessage(role=ChatRole.ASSISTANT, content=response_text)
            )
            self._task_ledger.complete_task(task_id, summary=response_text, success=True)

            await self._event_bus.publish(
                AgentCompleteEvent(
                    id=uuid.uuid4(),
                    source=EventSource.ORCHESTRATOR,
                    timestamp=datetime.now(UTC),
                    payload=AgentCompletePayload(
                        task_id=task_id, summary=response_text, success=True
                    ),
                )
            )

            return response_text

    # -- internals ---------------------------------------------------------

    async def _synthesize_response(
        self, task_id: uuid.UUID, conversation_id: uuid.UUID, plan: Plan
    ) -> str:
        observations_summary = "\n".join(
            f"- {o.detail}" for o in self._task_ledger.get_task(task_id).observations
        )
        context_messages = await self._memory.retrieve(conversation_id)

        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=_ORCHESTRATOR_SYSTEM_PROMPT),
            *context_messages,
        ]
        if observations_summary:
            messages.append(
                ChatMessage(
                    role=ChatRole.SYSTEM,
                    content=f"Internal agent findings:\n{observations_summary}",
                )
            )

        chunks: list[str] = []
        async for delta in self._model_router.stream(
            AiTaskType.CHAT, messages, task_id=task_id
        ):
            chunks.append(delta)
            await self._event_bus.publish(
                OrchestratorMessageEvent(
                    id=uuid.uuid4(),
                    source=EventSource.ORCHESTRATOR,
                    timestamp=datetime.now(UTC),
                    payload=OrchestratorMessagePayload(
                        conversation_id=conversation_id,
                        role=MessageRole.ASSISTANT,
                        content_delta=delta,
                        done=False,
                    ),
                )
            )

        await self._event_bus.publish(
            OrchestratorMessageEvent(
                id=uuid.uuid4(),
                source=EventSource.ORCHESTRATOR,
                timestamp=datetime.now(UTC),
                payload=OrchestratorMessagePayload(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    content_delta="",
                    done=True,
                ),
            )
        )

        return "".join(chunks)

    async def _publish_plan(self, task_id: uuid.UUID, plan: Plan) -> None:
        await self._event_bus.publish(
            AgentPlanEvent(
                id=uuid.uuid4(),
                source=EventSource.ORCHESTRATOR,
                timestamp=datetime.now(UTC),
                payload=AgentPlanPayload(
                    task_id=task_id,
                    steps=[
                        PlanStepSchema(
                            step_id=step.step_id,
                            description=step.description,
                            agent=step.agent,
                            tool=step.tool,
                        )
                        for step in plan.steps
                    ],
                ),
            )
        )

    async def _publish_step(self, task_id: uuid.UUID, step: PlanStep, status: TaskStatus) -> None:
        await self._event_bus.publish(
            AgentStepEvent(
                id=uuid.uuid4(),
                source=EventSource.ORCHESTRATOR,
                timestamp=datetime.now(UTC),
                payload=AgentStepPayload(
                    task_id=task_id,
                    step_id=step.step_id,
                    agent=step.agent,
                    status=status,
                    description=step.description,
                ),
            )
        )
