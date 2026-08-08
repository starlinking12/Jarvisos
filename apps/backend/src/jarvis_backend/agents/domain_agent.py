"""DomainAgent — the middle tier of the three-tier hierarchy (ADR-0008).

A DomainAgent never talks to the user and never invokes a tool handler
itself. It delegates tool steps to ToolExecutor, preserving the single
execution/authorization choke point, or performs reasoning-only work through
ModelRouter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from jarvis_contracts import AiTaskType, EventSource

from jarvis_backend.ai import ChatMessage, ChatRole, ModelRouter

from .tool_executor import ToolExecutor
from .types import Observation, PlanStep


@dataclass(slots=True, frozen=True)
class DomainAgentSpec:
    identity: EventSource
    description: str
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    system_prompt: str = "You are a focused internal reasoning module. Respond concisely."


class DomainAgent:
    def __init__(
        self, spec: DomainAgentSpec, *, model_router: ModelRouter, tool_executor: ToolExecutor
    ) -> None:
        self.spec = spec
        self._model_router = model_router
        self._tool_executor = tool_executor

    async def handle_step(self, task_id: uuid.UUID, step: PlanStep) -> Observation:
        if step.tool is not None:
            if step.tool not in self.spec.allowed_tools:
                return Observation(
                    step_id=step.step_id,
                    success=False,
                    detail=(
                        f"Agent '{self.spec.identity.value}' is not permitted to use "
                        f"tool '{step.tool}'."
                    ),
                )
            return await self._tool_executor.execute(task_id, step)

        return await self._reason(task_id, step)

    async def _reason(self, task_id: uuid.UUID, step: PlanStep) -> Observation:
        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=self.spec.system_prompt),
            ChatMessage(role=ChatRole.USER, content=step.description),
        ]
        result = await self._model_router.complete(
            AiTaskType.REASONING, messages, task_id=task_id
        )
        return Observation(step_id=step.step_id, success=True, detail=result.content)


def build_default_agent_specs() -> dict[EventSource, DomainAgentSpec]:
    """Return the named agents and their current capability allowlists.

    Phase-specific behavior is supplied by subclasses in the composition
    root. Keeping these specs data-only preserves the existing planner and
    agent-dispatch contracts.
    """
    return {
        EventSource.AGENT_DESKTOP: DomainAgentSpec(
            identity=EventSource.AGENT_DESKTOP,
            description="Understands and reasons about live desktop application state.",
            allowed_tools=frozenset({"desktop.list_windows", "desktop.active_window"}),
            system_prompt=(
                "You are the Desktop agent. Reason about applications, windows, "
                "and UI state using only verified observations."
            ),
        ),
        EventSource.AGENT_VISION: DomainAgentSpec(
            identity=EventSource.AGENT_VISION,
            description="Interprets screen/image content (Phase 6).",
            system_prompt=(
                "You are the Vision agent, operating in reasoning-only mode until "
                "image analysis tooling lands. Never claim to have visually inspected "
                "a screen when no vision tool was executed."
            ),
        ),
        EventSource.AGENT_RESEARCH: DomainAgentSpec(
            identity=EventSource.AGENT_RESEARCH,
            description="Gathers and synthesizes information.",
            system_prompt=(
                "You are the Research agent. Use only tools actually available to you "
                "and distinguish current observations from reasoning."
            ),
        ),
        EventSource.AGENT_SECURITY: DomainAgentSpec(
            identity=EventSource.AGENT_SECURITY,
            description="Monitors and reasons about system security posture.",
            system_prompt="You are the Security agent. Be precise about observed security state.",
        ),
        EventSource.AGENT_MEMORY: DomainAgentSpec(
            identity=EventSource.AGENT_MEMORY,
            description="Reasons about stored context and retrieval relevance.",
            allowed_tools=frozenset({"system.get_current_time"}),
            system_prompt="You are the Memory agent. Reason about context relevance precisely.",
        ),
        EventSource.AGENT_EARTH: DomainAgentSpec(
            identity=EventSource.AGENT_EARTH,
            description="Geospatial visualization and reasoning (Phase 6+).",
            system_prompt="You are the Earth agent. Geospatial tooling is not yet active.",
        ),
        EventSource.AGENT_AUTOMATION: DomainAgentSpec(
            identity=EventSource.AGENT_AUTOMATION,
            description="Executes safety-gated desktop automation sequences.",
            allowed_tools=frozenset(
                {
                    "automation.focus_window",
                    "automation.minimize_window",
                    "automation.maximize_window",
                    "automation.close_window",
                    "automation.mouse_position",
                    "automation.move_mouse",
                    "automation.click",
                    "automation.type_text",
                    "automation.press_key",
                    "automation.hotkey",
                    "automation.scroll",
                }
            ),
            system_prompt=(
                "You are the Automation agent. Execute desktop actions only through "
                "the provided tools. Never claim success without a successful tool "
                "observation. Prefer small, reversible actions and verify targets."
            ),
        ),
        EventSource.AGENT_DEVELOPER: DomainAgentSpec(
            identity=EventSource.AGENT_DEVELOPER,
            description="Reasons about code and development tasks.",
            allowed_tools=frozenset({"system.list_agents", "system.get_current_time"}),
            system_prompt=(
                "You are the Developer agent. Reason about code, architecture, and "
                "development tasks precisely and technically."
            ),
        ),
    }
