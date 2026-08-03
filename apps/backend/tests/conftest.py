"""Shared fixtures for the backend test suite.

`orchestrator` and its dependencies are built by hand here (not via
`main.build_orchestrator`) so tests can inject `MockProvider` and a
fresh, non-global `EventBus` instance — `main.build_orchestrator` is
covered separately by `test_main_composition.py`, which asserts it wires
the same pieces together correctly, without needing a live provider.
"""

from __future__ import annotations

import uuid

import pytest
from jarvis_contracts import AiTaskType, EventSource

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


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def mock_provider() -> MockProvider:
    return MockProvider(scripted_response="This is a mock response.")


def make_all_task_routing(provider_name: str = "mock", model: str = "mock-small") -> RoutingConfig:
    return RoutingConfig(
        rules=[
            RoutingRule(
                task_type=task_type,
                targets=[RoutingTarget(provider=provider_name, model=model)],
            )
            for task_type in AiTaskType
        ]
    )


@pytest.fixture
def model_router(mock_provider: MockProvider, event_bus: EventBus) -> ModelRouter:
    return ModelRouter(
        providers={"mock": mock_provider},
        routing=make_all_task_routing(),
        retry_policy=RetryPolicy(max_retries=1, base_backoff_s=0.01, max_backoff_s=0.02),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=4, max_tokens_per_request=1024),
        event_bus=event_bus,
    )


@pytest.fixture
def tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_system_tools(registry, agent_names=["orchestrator", "agent.developer"])
    return registry


@pytest.fixture
def safety_gate() -> SafetyGate:
    return SafetyGate(SafetyPolicy.production_default())


@pytest.fixture
def task_ledger() -> TaskLedger:
    return TaskLedger()


@pytest.fixture
def tool_executor(
    tool_registry: ToolRegistry,
    safety_gate: SafetyGate,
    task_ledger: TaskLedger,
    event_bus: EventBus,
) -> ToolExecutor:
    return ToolExecutor(
        registry=tool_registry,
        safety_gate=safety_gate,
        task_ledger=task_ledger,
        event_bus=event_bus,
    )


@pytest.fixture
def domain_agents(
    model_router: ModelRouter, tool_executor: ToolExecutor
) -> dict[EventSource, DomainAgent]:
    specs = build_default_agent_specs()
    return {
        identity: DomainAgent(spec, model_router=model_router, tool_executor=tool_executor)
        for identity, spec in specs.items()
    }


@pytest.fixture
def retrieval_pipeline(model_router: ModelRouter) -> RetrievalPipeline:
    return RetrievalPipeline(
        working_memory=WorkingMemory(),
        long_term_memory=NullLongTermMemory(),
        model_router=model_router,
    )


@pytest.fixture
def orchestrator(
    model_router: ModelRouter,
    tool_registry: ToolRegistry,
    task_ledger: TaskLedger,
    retrieval_pipeline: RetrievalPipeline,
    event_bus: EventBus,
    domain_agents: dict[EventSource, DomainAgent],
) -> Orchestrator:
    planner = SimplePlanner(model_router, tool_registry)
    return Orchestrator(
        model_router=model_router,
        planner=planner,
        task_ledger=task_ledger,
        memory=retrieval_pipeline,
        event_bus=event_bus,
        agents=domain_agents,
    )


@pytest.fixture
def new_conversation_id() -> uuid.UUID:
    return uuid.uuid4()
