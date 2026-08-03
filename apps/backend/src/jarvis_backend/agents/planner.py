"""Planner — turns a user goal into a `Plan` of steps assigned to domain
agents (and, where applicable, specific tools). See ADR-0008 for where the
Planner sits in the three-tier hierarchy.

`Planner` is a `Protocol`, not an ABC — same rationale as
`ModelProvider` in `ai/types.py`: structural typing keeps planner
implementations free of a required base-class import, so a future
plugin-supplied planner (Phase 4+) can satisfy the interface without
depending on this module at all.

`SimplePlanner` is the default, real implementation: it prompts the
routed reasoning model to decompose the goal into JSON-described steps,
parses the result defensively, and falls back to a single-step plan
(assigned to the Orchestrator itself, with no tool) if the model's output
isn't valid JSON — a genuine degradation path, not a placeholder, since a
plan of "one step: respond directly" is a completely valid plan for a
simple conversational goal.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Protocol

import structlog
from jarvis_contracts import AiTaskType, EventSource

from jarvis_backend.ai import ChatMessage, ChatRole, ModelRouter

from .tool_registry import ToolRegistry
from .types import Plan, PlanStep

logger = structlog.get_logger("jarvis_backend.agents.planner")

_PLANNER_SYSTEM_PROMPT = """You are the planning module of a local-first AI \
operating system. Decompose the user's goal into a short sequence of steps. \
Each step is handled by exactly one domain agent. Available agents: {agents}. \
Available tools (use only when a step genuinely needs one): {tools}.

Respond with ONLY a JSON array, no prose, no markdown fences. Each element:
{{"description": string, "agent": one of the available agents, \
"tool": tool name or null, "tool_args": object or {{}}}}

If the goal can be answered directly through conversation with no tool use, \
respond with a single-step plan assigned to "orchestrator" with "tool": null."""


class Planner(Protocol):
    async def plan(
        self,
        *,
        goal: str,
        task_id: uuid.UUID,
        available_agents: list[EventSource],
    ) -> Plan: ...


class SimplePlanner:
    def __init__(self, model_router: ModelRouter, tool_registry: ToolRegistry) -> None:
        self._model_router = model_router
        self._tool_registry = tool_registry

    async def plan(
        self,
        *,
        goal: str,
        task_id: uuid.UUID,
        available_agents: list[EventSource],
    ) -> Plan:
        system_prompt = _PLANNER_SYSTEM_PROMPT.format(
            agents=", ".join(a.value for a in available_agents),
            tools=self._tool_registry.describe_for_planner(),
        )
        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=system_prompt),
            ChatMessage(role=ChatRole.USER, content=goal),
        ]

        result = await self._model_router.complete(
            AiTaskType.REASONING, messages, task_id=task_id, temperature=0.2
        )

        steps = self._parse_steps(result.content, available_agents)
        if not steps:
            steps = [
                PlanStep(
                    step_id=uuid.uuid4(),
                    description="Respond directly to the user's request.",
                    agent=EventSource.ORCHESTRATOR,
                    tool=None,
                )
            ]

        return Plan(task_id=task_id, goal=goal, steps=steps)

    def _parse_steps(
        self, raw_content: str, available_agents: list[EventSource]
    ) -> list[PlanStep]:
        json_text = self._extract_json_array(raw_content)
        if json_text is None:
            logger.warning("planner_output_not_json", raw_content=raw_content[:200])
            return []

        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError:
            logger.warning("planner_output_invalid_json", raw_content=raw_content[:200])
            return []

        if not isinstance(parsed, list):
            return []

        valid_agent_values = {a.value for a in available_agents} | {EventSource.ORCHESTRATOR.value}
        steps: list[PlanStep] = []
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            agent_value = entry.get("agent")
            if agent_value not in valid_agent_values:
                continue
            steps.append(
                PlanStep(
                    step_id=uuid.uuid4(),
                    description=str(entry.get("description", "")),
                    agent=EventSource(agent_value),
                    tool=entry.get("tool") if isinstance(entry.get("tool"), str) else None,
                    tool_args=entry.get("tool_args")
                    if isinstance(entry.get("tool_args"), dict)
                    else {},
                )
            )
        return steps

    @staticmethod
    def _extract_json_array(text: str) -> str | None:
        # Models frequently wrap JSON in markdown fences despite
        # instructions not to — strip them defensively rather than fail the
        # whole plan over formatting noise.
        stripped = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        start = stripped.find("[")
        end = stripped.rfind("]")
        if start == -1 or end == -1 or end < start:
            return None
        return stripped[start : end + 1]
