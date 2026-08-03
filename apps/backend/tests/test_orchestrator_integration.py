from __future__ import annotations

import asyncio
import uuid

from jarvis_contracts import AiTaskType, EventSource, JarvisEvent, TaskStatus

from jarvis_backend.agents.domain_agent import DomainAgent, build_default_agent_specs
from jarvis_backend.agents.orchestrator import Orchestrator
from jarvis_backend.agents.planner import SimplePlanner
from jarvis_backend.agents.safety_gate import SafetyGate, SafetyPolicy
from jarvis_backend.agents.task_ledger import TaskLedger
from jarvis_backend.agents.tool_executor import ToolExecutor
from jarvis_backend.agents.tool_registry import ToolRegistry
from jarvis_backend.agents.tools.system_tools import register_system_tools
from jarvis_backend.ai import MockProvider, ModelRouter
from jarvis_backend.config import (
    ResourceLimits,
    RetryPolicy,
    RoutingConfig,
    RoutingRule,
    RoutingTarget,
)
from jarvis_backend.event_bus import EventBus
from jarvis_backend.memory import NullLongTermMemory, RetrievalPipeline, WorkingMemory


def _build_two_provider_orchestrator(
    *, plan_json: str, chat_response: str
) -> tuple[Orchestrator, EventBus, TaskLedger, WorkingMemory]:
    """Wires a full Orchestrator with two distinct mock providers — one
    that answers reasoning/planning calls, one that answers the final
    chat response — so the test can assert on each independently, unlike
    the single-provider fixtures in conftest.py."""
    planner_provider = MockProvider(scripted_response=plan_json)
    chat_provider = MockProvider(scripted_response=chat_response)
    event_bus = EventBus()

    routing = RoutingConfig(
        rules=[
            RoutingRule(
                task_type=AiTaskType.CHAT,
                targets=[RoutingTarget(provider="chat", model="mock-large")],
            ),
            RoutingRule(
                task_type=AiTaskType.REASONING,
                targets=[RoutingTarget(provider="planner", model="mock-small")],
            ),
            RoutingRule(
                task_type=AiTaskType.SUMMARIZE,
                targets=[RoutingTarget(provider="chat", model="mock-large")],
            ),
            RoutingRule(
                task_type=AiTaskType.TOOLCALL,
                targets=[RoutingTarget(provider="planner", model="mock-small")],
            ),
            RoutingRule(
                task_type=AiTaskType.EMBED,
                targets=[RoutingTarget(provider="planner", model="mock-small")],
            ),
        ]
    )

    model_router = ModelRouter(
        providers={"planner": planner_provider, "chat": chat_provider},
        routing=routing,
        retry_policy=RetryPolicy(max_retries=0),
        resource_limits=ResourceLimits(
            max_concurrent_ai_requests=4, max_tokens_per_request=1024
        ),
        event_bus=event_bus,
    )

    tool_registry = ToolRegistry()
    agent_specs = build_default_agent_specs()
    register_system_tools(
        tool_registry, agent_names=[spec.identity.value for spec in agent_specs.values()]
    )

    task_ledger = TaskLedger()
    safety_gate = SafetyGate(SafetyPolicy.production_default())
    tool_executor = ToolExecutor(
        registry=tool_registry,
        safety_gate=safety_gate,
        task_ledger=task_ledger,
        event_bus=event_bus,
    )

    agents: dict[EventSource, DomainAgent] = {
        identity: DomainAgent(spec, model_router=model_router, tool_executor=tool_executor)
        for identity, spec in agent_specs.items()
    }

    working_memory = WorkingMemory()
    retrieval = RetrievalPipeline(
        working_memory=working_memory,
        long_term_memory=NullLongTermMemory(),
        model_router=model_router,
    )
    planner = SimplePlanner(model_router, tool_registry)

    orchestrator = Orchestrator(
        model_router=model_router,
        planner=planner,
        task_ledger=task_ledger,
        memory=retrieval,
        event_bus=event_bus,
        agents=agents,
    )

    return orchestrator, event_bus, task_ledger, working_memory


async def _collect_events(
    event_bus: EventBus, *, until_type: str, timeout: float = 5.0
) -> list[JarvisEvent]:
    received: list[JarvisEvent] = []

    async def collect() -> None:
        async for event in event_bus.subscribe():
            received.append(event)
            if event.type == until_type:
                return

    await asyncio.wait_for(collect(), timeout=timeout)
    return received


async def test_full_lifecycle_direct_response_no_tools() -> None:
    orchestrator, event_bus, task_ledger, _working_memory = _build_two_provider_orchestrator(
        plan_json='[{"description": "respond directly", "agent": "orchestrator", '
        '"tool": null, "tool_args": {}}]',
        chat_response="Hello! How can I help you today?",
    )

    collector = asyncio.create_task(_collect_events(event_bus, until_type="agent.complete"))
    await asyncio.sleep(0)  # let the subscriber attach before publishing starts

    response = await orchestrator.handle_user_message(uuid.uuid4(), "hi there")
    events = await collector

    assert response == "Hello! How can I help you today?"

    event_types = [e.type for e in events]
    assert event_types[0] == "agent.task.created"
    assert "agent.plan" in event_types
    assert "agent.step" in event_types
    assert "orchestrator.message" in event_types
    assert event_types[-1] == "agent.complete"

    tasks = task_ledger.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].status == TaskStatus.COMPLETED


async def test_full_lifecycle_with_tool_dispatch_to_domain_agent() -> None:
    orchestrator, event_bus, task_ledger, _working_memory = _build_two_provider_orchestrator(
        plan_json='[{"description": "check the time", "agent": "agent.developer", '
        '"tool": "system.get_current_time", "tool_args": {}}]',
        chat_response="The current time has been retrieved.",
    )

    collector = asyncio.create_task(_collect_events(event_bus, until_type="agent.complete"))
    await asyncio.sleep(0)

    response = await orchestrator.handle_user_message(uuid.uuid4(), "what time is it?")
    events = await collector

    assert response == "The current time has been retrieved."
    event_types = [e.type for e in events]
    assert "agent.observe" in event_types

    observe_events = [e for e in events if e.type == "agent.observe"]
    assert observe_events[0].payload.success is True

    task = task_ledger.list_tasks()[0]
    assert len(task.observations) == 1
    assert task.observations[0].success is True


async def test_planning_failure_falls_back_gracefully() -> None:
    orchestrator, event_bus, task_ledger, _working_memory = _build_two_provider_orchestrator(
        plan_json="not valid json, will trigger fallback",
        chat_response="I can still respond directly.",
    )

    collector = asyncio.create_task(_collect_events(event_bus, until_type="agent.complete"))
    await asyncio.sleep(0)

    response = await orchestrator.handle_user_message(uuid.uuid4(), "goal")
    await collector

    assert response == "I can still respond directly."
    task = task_ledger.list_tasks()[0]
    assert task.status == TaskStatus.COMPLETED
    assert task.plan is not None
    assert len(task.plan.steps) == 1
    assert task.plan.steps[0].agent == EventSource.ORCHESTRATOR


async def test_conversation_history_persists_across_turns() -> None:
    orchestrator, event_bus, _task_ledger, working_memory = _build_two_provider_orchestrator(
        plan_json='[{"description": "respond", "agent": "orchestrator", '
        '"tool": null, "tool_args": {}}]',
        chat_response="Sure thing.",
    )
    conversation_id = uuid.uuid4()

    await orchestrator.handle_user_message(conversation_id, "first message")
    await orchestrator.handle_user_message(conversation_id, "second message")

    history = working_memory.get(conversation_id)
    contents = [m.content for m in history]
    assert "first message" in contents
    assert "second message" in contents
    assert contents.count("Sure thing.") == 2
