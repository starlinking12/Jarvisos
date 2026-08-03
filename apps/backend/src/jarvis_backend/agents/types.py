"""Core types for the agent framework.

These are the backend's internal, richer representations — e.g. `PlanStep`
carries `tool_args` that never need to cross the wire to the renderer, only
`PlanStepSchema` (the contract's summarized wire format, in
`jarvis_contracts.events`) does. Keeping them distinct avoids overloading
one schema with both "what the renderer needs to display" and "what the
executor needs to run," which is exactly the kind of coupling ADR-0008
identifies as the reason for a three-tier hierarchy in the first place.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from jarvis_contracts import EventSource, TaskStatus


@dataclass(slots=True, frozen=True)
class PlanStep:
    step_id: uuid.UUID
    description: str
    agent: EventSource
    tool: str | None = None
    tool_args: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class Plan:
    task_id: uuid.UUID
    goal: str
    steps: list[PlanStep]


@dataclass(slots=True, frozen=True)
class Observation:
    step_id: uuid.UUID
    success: bool
    detail: str


@dataclass(slots=True)
class AgentTask:
    """The Task Ledger's unit of record. Mutable (status/plan/observations
    accumulate over the task's lifetime) but only ever mutated by
    `TaskLedger`, never by agents directly — see ADR-0008."""

    task_id: uuid.UUID
    goal: str
    requested_by: EventSource
    created_at: datetime
    status: TaskStatus = TaskStatus.QUEUED
    plan: Plan | None = None
    observations: list[Observation] = field(default_factory=list)
    summary: str | None = None
