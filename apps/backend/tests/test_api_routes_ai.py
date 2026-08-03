from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jarvis_contracts import EventSource

from jarvis_backend.agents.domain_agent import DomainAgent, build_default_agent_specs
from jarvis_backend.agents.orchestrator import Orchestrator
from jarvis_backend.agents.planner import SimplePlanner
from jarvis_backend.agents.safety_gate import SafetyGate, SafetyPolicy
from jarvis_backend.agents.task_ledger import TaskLedger
from jarvis_backend.agents.tool_executor import ToolExecutor
from jarvis_backend.agents.tool_registry import ToolRegistry
from jarvis_backend.agents.tools.system_tools import register_system_tools
from jarvis_backend.ai import MockProvider, ModelRouter
from jarvis_backend.api.routes_ai import router as ai_router
from jarvis_backend.config import ResourceLimits, RetryPolicy
from jarvis_backend.event_bus import EventBus
from jarvis_backend.memory import NullLongTermMemory, RetrievalPipeline, WorkingMemory

from .conftest import make_all_task_routing


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(ai_router)

    provider = MockProvider(scripted_response="Hello from the test API.")
    event_bus = EventBus()
    model_router = ModelRouter(
        providers={"mock": provider},
        routing=make_all_task_routing(),
        retry_policy=RetryPolicy(max_retries=0),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=event_bus,
    )
    tool_registry = ToolRegistry()
    specs = build_default_agent_specs()
    register_system_tools(tool_registry, agent_names=[s.identity.value for s in specs.values()])
    task_ledger = TaskLedger()
    tool_executor = ToolExecutor(
        registry=tool_registry,
        safety_gate=SafetyGate(SafetyPolicy.production_default()),
        task_ledger=task_ledger,
        event_bus=event_bus,
    )
    agents: dict[EventSource, DomainAgent] = {
        identity: DomainAgent(spec, model_router=model_router, tool_executor=tool_executor)
        for identity, spec in specs.items()
    }
    retrieval = RetrievalPipeline(
        working_memory=WorkingMemory(),
        long_term_memory=NullLongTermMemory(),
        model_router=model_router,
    )
    orchestrator = Orchestrator(
        model_router=model_router,
        planner=SimplePlanner(model_router, tool_registry),
        task_ledger=task_ledger,
        memory=retrieval,
        event_bus=event_bus,
        agents=agents,
    )
    app.state.orchestrator = orchestrator
    return app


def test_post_chat_returns_orchestrator_response() -> None:
    app = _build_test_app()
    client = TestClient(app)
    conversation_id = str(uuid.uuid4())

    response = client.post(
        "/ai/chat", json={"conversationId": conversation_id, "message": "hello"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversationId"] == conversation_id
    assert isinstance(body["response"], str)
    assert len(body["response"]) > 0


def test_post_chat_rejects_missing_message_field() -> None:
    app = _build_test_app()
    client = TestClient(app)

    response = client.post("/ai/chat", json={"conversationId": str(uuid.uuid4())})

    assert response.status_code == 422


def test_post_chat_rejects_invalid_conversation_id() -> None:
    app = _build_test_app()
    client = TestClient(app)

    response = client.post(
        "/ai/chat", json={"conversationId": "not-a-uuid", "message": "hi"}
    )

    assert response.status_code == 422
