"""TaskLedger — the authoritative record of every agent task's lifecycle.

Every mutation (creation, plan assignment, observation, completion) is
audit-logged via structlog with the task id bound as `correlation_id`, so
the full lifecycle of any task can be reconstructed from logs alone.

**Phase 4 update:** storage is now durable when a `TaskRepository`-shaped
object is provided (writes through to SQLite on every mutation — see
`persistence/repositories/task_repository.py`), fulfilling the promise
made in ADR-0004/ADR-0007 that Phase 4's persistence layer would change
`TaskLedger`'s internals without touching its public interface. An
in-process dict remains as a read-through cache (avoids a DB round trip
for every `get_task`/`list_tasks` call within one backend session); the
repository is the durable source of truth surviving restarts.

The repository dependency is expressed as `TaskRepositoryProtocol`
(structural typing, the same `Protocol`-based pattern as `ModelProvider`/
`VadProvider`/every other provider in this codebase), not a direct import
of the concrete `TaskRepository` class — this keeps `agents/` free of a
hard dependency on `persistence/`, consistent with ADR-0012's dependency
direction (persistence depends on agents' types, not the reverse).
Passing no repository (the default) restores Phase 2/3's in-memory-only
behavior exactly, so no existing test needed to change.
"""

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

    def _require(self, task_id: uuid.UUID) -> AgentTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"No task with id {task_id}")
        return task

    def _persist(self, write_coro: object) -> None:
        """Fires a persistence write-through without making every
        `TaskLedger` method async — `Orchestrator`'s call sites are
        already inside `async def` methods on the event loop, so
        scheduling via `asyncio.ensure_future` runs the write concurrently
        with whatever the caller does next rather than serializing every
        mutation behind a DB round trip. A failed write is logged, not
        raised — durability is a best-effort enhancement layered on top
        of the always-correct in-memory ledger, not a new failure mode
        for agent execution to handle. No-ops entirely when no repository
        was configured (`write_coro` is `None`).
        """
        if write_coro is None:
            return

        async def _run() -> None:
            try:
                await write_coro  # type: ignore[misc] - Awaitable[None] narrowed
                # at the two call-site branches above; Protocol methods don't
                # give us a cleaner static type for "the coroutine this
                # specific call produced" without one overload per method.
            except Exception:  # noqa: BLE001 - persistence failures must never
                # crash agent execution; they're logged and the in-memory
                # ledger (already updated by the caller) remains correct.
                audit_logger.warning("task_persistence_write_failed", exc_info=True)

        asyncio.ensure_future(_run())
