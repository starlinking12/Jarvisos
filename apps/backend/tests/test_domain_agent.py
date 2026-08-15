from __future__ import annotations

import uuid

from jarvis_contracts import EventSource

from jarvis_backend.agents.domain_agent import (
    DomainAgent,
    DomainAgentSpec,
    build_default_agent_specs,
)
from jarvis_backend.agents.safety_gate import SafetyGate, SafetyPolicy
from jarvis_backend.agents.task_ledger import TaskLedger
from jarvis_backend.agents.tool_executor import ToolExecutor
from jarvis_backend.agents.tool_registry import ToolRegistry, ToolSpec
from jarvis_backend.agents.types import PlanStep
from jarvis_backend.ai import MockProvider, ModelRouter
from jarvis_backend.config import ResourceLimits, RetryPolicy
from jarvis_backend.event_bus import EventBus

from .conftest import make_all_task_routing


def test_build_default_agent_specs_covers_all_eight_agents() -> None:
    specs = build_default_agent_specs()
    expected = {
        EventSource.AGENT_DESKTOP,
        EventSource.AGENT_VISION,
        EventSource.AGENT_RESEARCH,
        EventSource.AGENT_SECURITY,
        EventSource.AGENT_MEMORY,
        EventSource.AGENT_EARTH,
        EventSource.AGENT_AUTOMATION,
        EventSource.AGENT_DEVELOPER,
    }
    assert set(specs.keys()) == expected
    for identity, spec in specs.items():
        assert spec.identity == identity


async def test_domain_agent_delegates_allowed_tool_to_executor() -> None:
    async def handler(args: dict[str, object]) -> str:
        return "tool ran"

    registry = ToolRegistry()
    registry.register(ToolSpec(name="allowed.tool", description="allowed", handler=handler))
    task_ledger = TaskLedger()
    task = task_ledger.create_task(goal="delegate tool", requested_by=EventSource.ORCHESTRATOR)
    executor = ToolExecutor(
        registry=registry,
        safety_gate=SafetyGate(SafetyPolicy.production_default()),
        task_ledger=task_ledger,
        event_bus=EventBus(),
    )
    router = ModelRouter(
        providers={"mock": MockProvider()},
        routing=make_all_task_routing(),
        retry_policy=RetryPolicy(max_retries=0),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=EventBus(),
    )
    spec = DomainAgentSpec(
        identity=EventSource.AGENT_DEVELOPER,
        description="test agent",
        allowed_tools=frozenset({"allowed.tool"}),
    )
    agent = DomainAgent(spec, model_router=router, tool_executor=executor)

    step = PlanStep(
        step_id=uuid.uuid4(),
        description="use the tool",
        agent=EventSource.AGENT_DEVELOPER,
        tool="allowed.tool",
    )

    observation = await agent.handle_step(task.task_id, step)

    assert observation.success is True
    assert observation.detail == "tool ran"


async def test_domain_agent_rejects_disallowed_tool() -> None:
    registry = ToolRegistry()
    task_ledger = TaskLedger()
    task = task_ledger.create_task(goal="reject tool", requested_by=EventSource.ORCHESTRATOR)
    executor = ToolExecutor(
        registry=registry,
        safety_gate=SafetyGate(SafetyPolicy.production_default()),
        task_ledger=task_ledger,
        event_bus=EventBus(),
    )
    router = ModelRouter(
        providers={"mock": MockProvider()},
        routing=make_all_task_routing(),
        retry_policy=RetryPolicy(max_retries=0),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=EventBus(),
    )
    spec = DomainAgentSpec(
        identity=EventSource.AGENT_VISION,
        description="test agent",
        allowed_tools=frozenset(),  # nothing allowed
    )
    agent = DomainAgent(spec, model_router=router, tool_executor=executor)

    step = PlanStep(
        step_id=uuid.uuid4(),
        description="try a disallowed tool",
        agent=EventSource.AGENT_VISION,
        tool="system.get_current_time",
    )

    observation = await agent.handle_step(task.task_id, step)

    assert observation.success is False
    assert "not permitted" in observation.detail


async def test_domain_agent_reasons_when_no_tool_specified() -> None:
    registry = ToolRegistry()
    executor = ToolExecutor(
        registry=registry,
        safety_gate=SafetyGate(SafetyPolicy.production_default()),
        task_ledger=TaskLedger(),
        event_bus=EventBus(),
    )
    router = ModelRouter(
        providers={"mock": MockProvider(scripted_response="reasoned answer")},
        routing=make_all_task_routing(),
        retry_policy=RetryPolicy(max_retries=0),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=EventBus(),
    )
    spec = DomainAgentSpec(identity=EventSource.AGENT_RESEARCH, description="test agent")
    agent = DomainAgent(spec, model_router=router, tool_executor=executor)

    step = PlanStep(
        step_id=uuid.uuid4(),
        description="think about this",
        agent=EventSource.AGENT_RESEARCH,
        tool=None,
    )

    observation = await agent.handle_step(uuid.uuid4(), step)

    assert observation.success is True
    assert observation.detail == "reasoned answer"
