"""TaskRepository — durable persistence for `TaskLedger` (ADR-0004).

Phase 2's `TaskLedger` was explicitly documented as in-process/non-durable
pending Phase 4's persistence layer (ADR-0004 §Consequences, ADR-0007
§Consequences). This repository is that persistence layer's task-facing
half — `TaskLedger`'s public interface does not change; only its internal
storage does, exactly as both ADRs predicted.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import aiosqlite
from jarvis_contracts import EventSource, TaskStatus

from jarvis_backend.agents.types import AgentTask, Observation, Plan, PlanStep

from ..database import Database


class TaskRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def insert_task(self, task: AgentTask) -> None:
        await self._db.execute(
            """
            INSERT INTO tasks (task_id, goal, requested_by, status, created_at, summary, plan_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(task.task_id),
                task.goal,
                task.requested_by.value,
                task.status.value,
                task.created_at.isoformat(),
                task.summary,
                self._plan_to_json(task.plan),
            ),
        )

    async def update_task(self, task: AgentTask) -> None:
        await self._db.execute(
            """
            UPDATE tasks SET status = ?, summary = ?, plan_json = ? WHERE task_id = ?
            """,
            (
                task.status.value,
                task.summary,
                self._plan_to_json(task.plan),
                str(task.task_id),
            ),
        )

    async def insert_observation(self, task_id: uuid.UUID, observation: Observation) -> None:
        await self._db.execute(
            """
            INSERT INTO task_observations (task_id, step_id, success, detail, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(task_id),
                str(observation.step_id),
                1 if observation.success else 0,
                observation.detail,
                datetime.now().isoformat(),
            ),
        )

    async def get_task(self, task_id: uuid.UUID) -> AgentTask | None:
        row = await self._db.fetch_one("SELECT * FROM tasks WHERE task_id = ?", (str(task_id),))
        if row is None:
            return None
        observations = await self._get_observations(task_id)
        return self._row_to_task(row, observations)

    async def list_tasks(self, limit: int = 100) -> list[AgentTask]:
        rows = await self._db.fetch_all(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        tasks = []
        for row in rows:
            task_id = uuid.UUID(row["task_id"])
            observations = await self._get_observations(task_id)
            tasks.append(self._row_to_task(row, observations))
        return tasks

    async def _get_observations(self, task_id: uuid.UUID) -> list[Observation]:
        rows = await self._db.fetch_all(
            "SELECT * FROM task_observations WHERE task_id = ? ORDER BY id ASC",
            (str(task_id),),
        )
        return [
            Observation(
                step_id=uuid.UUID(row["step_id"]),
                success=bool(row["success"]),
                detail=row["detail"],
            )
            for row in rows
        ]

    @staticmethod
    def _plan_to_json(plan: Plan | None) -> str | None:
        if plan is None:
            return None
        return json.dumps(
            {
                "task_id": str(plan.task_id),
                "goal": plan.goal,
                "steps": [
                    {
                        "step_id": str(step.step_id),
                        "description": step.description,
                        "agent": step.agent.value,
                        "tool": step.tool,
                        "tool_args": step.tool_args,
                    }
                    for step in plan.steps
                ],
            }
        )

    @staticmethod
    def _plan_from_json(raw: str | None) -> Plan | None:
        if raw is None:
            return None
        data = json.loads(raw)
        return Plan(
            task_id=uuid.UUID(data["task_id"]),
            goal=data["goal"],
            steps=[
                PlanStep(
                    step_id=uuid.UUID(step["step_id"]),
                    description=step["description"],
                    agent=EventSource(step["agent"]),
                    tool=step["tool"],
                    tool_args=step["tool_args"],
                )
                for step in data["steps"]
            ],
        )

    @classmethod
    def _row_to_task(cls, row: aiosqlite.Row, observations: list[Observation]) -> AgentTask:
        return AgentTask(
            task_id=uuid.UUID(row["task_id"]),
            goal=row["goal"],
            requested_by=EventSource(row["requested_by"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            status=TaskStatus(row["status"]),
            plan=cls._plan_from_json(row["plan_json"]),
            observations=observations,
            summary=row["summary"],
        )
