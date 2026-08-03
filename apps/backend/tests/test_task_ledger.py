from __future__ import annotations

import uuid

import pytest
from jarvis_contracts import EventSource, TaskStatus

from jarvis_backend.agents.task_ledger import TaskLedger, TaskNotFoundError
from jarvis_backend.agents.types import Observation, Plan


def test_create_task_initializes_queued_status() -> None:
    ledger = TaskLedger()
    task = ledger.create_task(goal="do something", requested_by=EventSource.ORCHESTRATOR)

    assert task.status == TaskStatus.QUEUED
    assert task.goal == "do something"
    assert task.observations == []


def test_set_plan_transitions_to_running() -> None:
    ledger = TaskLedger()
    task = ledger.create_task(goal="goal", requested_by=EventSource.ORCHESTRATOR)
    plan = Plan(task_id=task.task_id, goal="goal", steps=[])

    ledger.set_plan(task.task_id, plan)

    updated = ledger.get_task(task.task_id)
    assert updated.status == TaskStatus.RUNNING
    assert updated.plan is plan


def test_record_observation_appends_to_task() -> None:
    ledger = TaskLedger()
    task = ledger.create_task(goal="goal", requested_by=EventSource.ORCHESTRATOR)
    observation = Observation(step_id=uuid.uuid4(), success=True, detail="did it")

    ledger.record_observation(task.task_id, observation)

    assert ledger.get_task(task.task_id).observations == [observation]


def test_complete_task_success_sets_completed_status() -> None:
    ledger = TaskLedger()
    task = ledger.create_task(goal="goal", requested_by=EventSource.ORCHESTRATOR)

    ledger.complete_task(task.task_id, summary="done", success=True)

    updated = ledger.get_task(task.task_id)
    assert updated.status == TaskStatus.COMPLETED
    assert updated.summary == "done"


def test_complete_task_failure_sets_failed_status() -> None:
    ledger = TaskLedger()
    task = ledger.create_task(goal="goal", requested_by=EventSource.ORCHESTRATOR)

    ledger.complete_task(task.task_id, summary="failed", success=False)

    assert ledger.get_task(task.task_id).status == TaskStatus.FAILED


def test_get_task_raises_for_unknown_id() -> None:
    ledger = TaskLedger()
    with pytest.raises(TaskNotFoundError):
        ledger.get_task(uuid.uuid4())


def test_list_tasks_returns_all_created_tasks() -> None:
    ledger = TaskLedger()
    first = ledger.create_task(goal="a", requested_by=EventSource.ORCHESTRATOR)
    second = ledger.create_task(goal="b", requested_by=EventSource.ORCHESTRATOR)

    ids = {task.task_id for task in ledger.list_tasks()}
    assert ids == {first.task_id, second.task_id}
