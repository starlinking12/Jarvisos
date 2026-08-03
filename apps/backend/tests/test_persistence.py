from __future__ import annotations

import asyncio
import uuid

import pytest
from jarvis_contracts import EventSource, TaskStatus

from jarvis_backend.agents.task_ledger import TaskLedger
from jarvis_backend.agents.types import Observation, Plan
from jarvis_backend.ai import MockProvider, ModelRouter
from jarvis_backend.config import ResourceLimits, RetryPolicy
from jarvis_backend.event_bus import EventBus
from jarvis_backend.memory.sqlite_long_term_memory import SqliteLongTermMemory
from jarvis_backend.persistence import Database
from jarvis_backend.persistence.repositories import MemoryRepository, TaskRepository

from .conftest import make_all_task_routing


@pytest.fixture
async def database(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.connect()
    yield db
    await db.close()


def _make_router() -> ModelRouter:
    return ModelRouter(
        providers={"mock": MockProvider()},
        routing=make_all_task_routing(),
        retry_policy=RetryPolicy(max_retries=0),
        resource_limits=ResourceLimits(max_concurrent_ai_requests=2, max_tokens_per_request=512),
        event_bus=EventBus(),
    )


async def test_database_migrates_schema_on_connect(database: Database) -> None:
    tables = await database.fetch_all(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    )
    table_names = {row["name"] for row in tables}
    assert "tasks" in table_names
    assert "memory_items" in table_names
    assert "settings" in table_names
    assert "security_alerts" in table_names


async def test_task_repository_round_trip(database: Database) -> None:
    repository = TaskRepository(database)
    ledger = TaskLedger(repository=repository)

    task = ledger.create_task(goal="test durable task", requested_by=EventSource.ORCHESTRATOR)
    plan = Plan(task_id=task.task_id, goal="test durable task", steps=[])
    ledger.set_plan(task.task_id, plan)
    ledger.record_observation(
        task.task_id, Observation(step_id=uuid.uuid4(), success=True, detail="did it")
    )
    ledger.complete_task(task.task_id, summary="done", success=True)

    # Give the fire-and-forget persistence writes a chance to complete.
    await asyncio.sleep(0.05)

    persisted = await repository.get_task(task.task_id)
    assert persisted is not None
    assert persisted.status == TaskStatus.COMPLETED
    assert persisted.summary == "done"
    assert len(persisted.observations) == 1


async def test_task_ledger_without_repository_behaves_exactly_as_before() -> None:
    """Confirms ADR-0012's compatibility promise: omitting the repository
    restores Phase 2/3 in-memory-only behavior exactly."""
    ledger = TaskLedger()  # no repository
    task = ledger.create_task(goal="in-memory only", requested_by=EventSource.ORCHESTRATOR)
    assert ledger.get_task(task.task_id).goal == "in-memory only"


async def test_sqlite_long_term_memory_store_and_retrieve(database: Database) -> None:
    repository = MemoryRepository(database)
    memory = SqliteLongTermMemory(repository, _make_router())

    stored = await memory.store("the user prefers dark mode", source="test")
    assert stored.content == "the user prefers dark mode"

    results = await memory.retrieve("dark mode preference", limit=5)
    assert len(results) == 1
    assert results[0].content == "the user prefers dark mode"
    assert results[0].relevance_score is not None


async def test_sqlite_long_term_memory_retrieve_empty_when_nothing_stored(
    database: Database,
) -> None:
    repository = MemoryRepository(database)
    memory = SqliteLongTermMemory(repository, _make_router())

    results = await memory.retrieve("anything")
    assert results == []


async def test_sqlite_long_term_memory_relationships(database: Database) -> None:
    repository = MemoryRepository(database)
    memory = SqliteLongTermMemory(repository, _make_router())

    item_a = await memory.store("Project Atlas kickoff")
    item_b = await memory.store("Project Atlas deadline is Friday")
    await memory.add_relationship(item_a.item_id, item_b.item_id, "relates_to")

    related = await memory.related_items(item_a.item_id)
    assert (item_b.item_id, "relates_to") in related
