from __future__ import annotations

import uuid

from jarvis_contracts import EventSource

from jarvis_backend.agents.planner import SimplePlanner
from jarvis_backend.agents.tool_registry import ToolRegistry
from jarvis_backend.ai import MockProvider, ModelRouter
from jarvis_backend.config import ResourceLimits, RetryPolicy
from jarvis_backend.event_bus import EventBus

from .conftest import make_all_task_routing


def _make_router(scripted_response: str) -> ModelRouter:
    provider = MockProvider(scripted_response=scripted_response)
    return ModelRouter(
        providers={"mock": provider},
        routing=make_all_task_routing(),
        retry_policy=RetryPolicy(max_retries=0),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=EventBus(),
    )


async def test_planner_parses_valid_json_plan() -> None:
    scripted = (
        '[{"description": "look something up", "agent": "agent.research", '
        '"tool": null, "tool_args": {}}]'
    )
    router = _make_router(scripted)
    planner = SimplePlanner(router, ToolRegistry())

    plan = await planner.plan(
        goal="look something up",
        task_id=uuid.uuid4(),
        available_agents=[EventSource.AGENT_RESEARCH],
    )

    assert len(plan.steps) == 1
    assert plan.steps[0].agent == EventSource.AGENT_RESEARCH
    assert plan.steps[0].tool is None


async def test_planner_strips_markdown_fences() -> None:
    scripted = (
        '```json\n[{"description": "step one", "agent": "orchestrator", '
        '"tool": null, "tool_args": {}}]\n```'
    )
    router = _make_router(scripted)
    planner = SimplePlanner(router, ToolRegistry())

    plan = await planner.plan(goal="goal", task_id=uuid.uuid4(), available_agents=[])

    assert len(plan.steps) == 1
    assert plan.steps[0].agent == EventSource.ORCHESTRATOR


async def test_planner_falls_back_to_single_step_on_malformed_output() -> None:
    router = _make_router("this is not JSON at all")
    planner = SimplePlanner(router, ToolRegistry())

    plan = await planner.plan(goal="goal", task_id=uuid.uuid4(), available_agents=[])

    assert len(plan.steps) == 1
    assert plan.steps[0].agent == EventSource.ORCHESTRATOR
    assert plan.steps[0].tool is None


async def test_planner_filters_out_steps_with_invalid_agent_names() -> None:
    scripted = (
        '[{"description": "valid step", "agent": "agent.developer", '
        '"tool": null, "tool_args": {}}, '
        '{"description": "invalid step", "agent": "not_a_real_agent", '
        '"tool": null, "tool_args": {}}]'
    )
    router = _make_router(scripted)
    planner = SimplePlanner(router, ToolRegistry())

    plan = await planner.plan(
        goal="goal",
        task_id=uuid.uuid4(),
        available_agents=[EventSource.AGENT_DEVELOPER],
    )

    assert len(plan.steps) == 1
    assert plan.steps[0].agent == EventSource.AGENT_DEVELOPER
