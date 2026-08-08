"""DomainAgent — the middle tier of the three-tier hierarchy (ADR-0008).

A `DomainAgent` never talks to the user (only the Orchestrator does, per
the project mandate) and never invokes a tool's handler directly (only
`ToolExecutor` does). Its job is exactly one thing: given a `PlanStep`
assigned to it, either delegate to `ToolExecutor` (when the step names a
tool) or produce a reasoning-only observation via `ModelRouter` (when the
step is pure analysis/response drafting with no external action).

Most domain agents remain generic and are differentiated by `DomainAgentSpec`.
Phase 5 graduates the Desktop Agent to a bespoke subclass because it now has
real desktop-state behavior; Automation remains data-driven until it needs
agent-specific behavior beyond the shared tool delegation path.
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
    """The eight named domain agents from the project mandate.

    Phase 5 gives Desktop read-only desktop inspection tools and Automation
    the mutating desktop-control tools. SecurityGate remains the independent
    authorization layer for all `automation.input` operations.
    """
    return {
        EventSource.AGENT_DESKTOP: DomainAgentSpec(
            identity=EventSource.AGENT_DESKTOP,
            description="Understands desktop applications, windows, and native UI state.",
            allowed_tools=frozenset({
                "system.list_agents",
                "desktop.list_windows",
                "desktop.active_window",
                "desktop.inspect_ui",
            }),
            system_prompt="You are the Desktop agent. You reason about applications, "
            "windows, and native UI state. Use verified desktop observations when available. "
            "Never claim to have changed the desktop yourself; mutating actions belong to "
            "the Automation agent.",
        ),
        EventSource.AGENT_VISION: DomainAgentSpec(
            identity=EventSource.AGENT_VISION,
            description="Interprets screen/image content (Phase 6).",
            system_prompt="You are the Vision agent, operating in reasoning-only mode "
            "until image analysis tooling lands. Be explicit about this limitation "
            "if the step requires actual image interpretation.",
        ),
        EventSource.AGENT_RESEARCH: DomainAgentSpec(
            identity=EventSource.AGENT_RESEARCH,
            description="Gathers and synthesizes information (future research tooling).",
            system_prompt="You are the Research agent, operating in reasoning-only mode "
            "until search tooling lands. Be explicit about this limitation if the step "
            "requires live information you don't have.",
        ),
        EventSource.AGENT_SECURITY: DomainAgentSpec(
            identity=EventSource.AGENT_SECURITY,
            description="Monitors and reasons about system security posture (Phase 4).",
            system_prompt="You are the Security agent. You reason about the security findings "
            "provided by the Security Center and should not invent telemetry.",
        ),
        EventSource.AGENT_MEMORY: DomainAgentSpec(
            identity=EventSource.AGENT_MEMORY,
            description="Reasons about stored context and retrieval relevance.",
            allowed_tools=frozenset({"system.get_current_time"}),
            system_prompt="You are the Memory agent. You reason about what context is "
            "relevant to the current goal.",
        ),
        EventSource.AGENT_EARTH: DomainAgentSpec(
            identity=EventSource.AGENT_EARTH,
            description="Geospatial visualization and reasoning (Phase 6+).",
            system_prompt="You are the Earth agent, operating in reasoning-only mode "
            "until geospatial tooling lands.",
        ),
        EventSource.AGENT_AUTOMATION: DomainAgentSpec(
            identity=EventSource.AGENT_AUTOMATION,
            description="Executes gated desktop automation sequences.",
            allowed_tools=frozenset({
                "automation.focus_window",
                "automation.move_window",
                "automation.resize_window",
                "automation.click",
                "automation.type_text",
                "automation.press_key",
                "automation.hotkey",
                "automation.scroll",
            }),
            system_prompt="You are the Automation agent. You execute only concrete desktop "
            "actions represented by registered automation tools. Never claim an action was "
            "performed unless the tool returned success.",
        ),
        EventSource.AGENT_DEVELOPER: DomainAgentSpec(
            identity=EventSource.AGENT_DEVELOPER,
            description="Reasons about code and development tasks.",
            allowed_tools=frozenset({"system.list_agents", "system.get_current_time"}),
            system_prompt="You are the Developer agent. You reason about code, "
            "architecture, and development tasks precisely and technically.",
        ),
    }
