"""TaskLedger — authoritative record of every agent task's lifecycle."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Protocol

import structlog
from jarvis_contracts import EventSource, TaskStatus

from .types import AgentTask, Observation, Plan

audit_logger = structlog.get_logger("jarvis_backend.audit")


class TaskNotFoundError(KeyError):
    pass


class TaskRepositoryProtocol(Protocol):
    async def insert_task(self, task: AgentTask) -> None: ...
    async def update_task(self, task: AgentTask) -> None: ...
    async def insert_observation(self, task_id: uuid.UUID, observation: Observation) -> None: ...


class TaskLedger:
    def __init__(self, repository: TaskRepositoryProtocol | None = None) -> None:
        self._tasks: dict[uuid.UUID, AgentTask] = {}
        self._repository = repository
        self._pending_writes: set[asyncio.Task[None]] = set()

    def create_task(self, *, goal: str, requested_by: EventSource) -> AgentTask:
        task = AgentTask(
            task_id=uuid.uuid4(),
            goal=goal,
            requested_by=requested_by,
            created_at=datetime.now(UTC),
        )
        self._tasks[task.task_id] = task
        audit_logger.info(
            "task_created",
            correlation_id=str(task.task_id),
            goal=goal,
            requested_by=requested_by.value,
        )
        self._persist(self._repository.insert_task(task) if self._repository else None)
        return task

    def set_plan(self, task_id: uuid.UUID, plan: Plan) -> None:
        task = self._require(task_id)
        task.plan = plan
        task.status = TaskStatus.RUNNING
        audit_logger.info(
            "task_plan_set",
            correlation_id=str(task_id),
            step_count=len(plan.steps),
        )
        self._persist(self._repository.update_task(task) if self._repository else None)

    def set_status(self, task_id: uuid.UUID, status: TaskStatus) -> None:
        task = self._require(task_id)
        task.status = status
        audit_logger.info("task_status_changed", correlation_id=str(task_id), status=status.value)
        self._persist(self._repository.update_task(task) if self._repository else None)

    def record_observation(self, task_id: uuid.UUID, observation: Observation) -> None:
        task = self._require(task_id)
        task.observations.append(observation)
        audit_logger.info(
            "task_observation_recorded",
            correlation_id=str(task_id),
            step_id=str(observation.step_id),
            success=observation.success,
        )
        self._persist(
            self._repository.insert_observation(task_id, observation)
            if self._repository
            else None
        )

    def complete_task(self, task_id: uuid.UUID, *, summary: str, success: bool) -> AgentTask:
        task = self._require(task_id)
        task.summary = summary
        task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        audit_logger.info(
            "task_completed",
            correlation_id=str(task_id),
            success=success,
            summary=summary,
        )
        self._persist(self._repository.update_task(task) if self._repository else None)
        return task

    def get_task(self, task_id: uuid.UUID) -> AgentTask:
        return self._require(task_id)

    def list_tasks(self) -> list[AgentTask]:
        return list(self._tasks.values())

    async def flush_persistence(self) -> None:
        """Drain outstanding write-through tasks before database shutdown."""
        while self._pending_writes:
            await asyncio.gather(*tuple(self._pending_writes), return_exceptions=True)

    def _require(self, task_id: uuid.UUID) -> AgentTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"No task with id {task_id}")
        return task

    def _persist(self, write_coro: object) -> None:
        """Schedule persistence and retain a strong reference until completion."""
        if write_coro is None:
            return

        async def _run() -> None:
            try:
                await write_coro  # type: ignore[misc]
            except Exception:  # noqa: BLE001 - durability must not abort execution
                audit_logger.warning("task_persistence_write_failed", exc_info=True)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        task = loop.create_task(_run(), name="task-ledger-persistence")
        self._pending_writes.add(task)
        task.add_done_callback(self._pending_writes.discard)
