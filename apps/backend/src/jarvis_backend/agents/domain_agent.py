"""DomainAgent — the middle tier of the three-tier hierarchy (ADR-0008).

A `DomainAgent` never talks to the user (only the Orchestrator does, per
the project mandate) and never invokes a tool's handler directly (only
`ToolExecutor` does). Its job is exactly one thing: given a `PlanStep`
assigned to it, either delegate to `ToolExecutor` (when the step names a
tool) or produce a reasoning-only observation via `ModelRouter` (when the
step is pure analysis/response drafting with no external action).

**Why one generic class for all eight named agents, not eight bespoke
classes:** in Phase 2, every domain agent's actual capability is "run a
tool from its allowed set, or reason about the step" — the same operation
for all of them. What differs between a Vision agent and a Developer agent
is WHICH tools they're allowed to use and what system-prompt framing they
bring to reasoning-only steps, both of which are *data* (`DomainAgentSpec`),
not *behavior*. Giving each agent its own class today, before any of them
has agent-specific behavior beyond that, would be eight files implementing
the same logic — exactly the duplication the project mandate prohibits.
Vision, Automation, Earth, and Security gain real bespoke behavior in their
respective phases (5, 4, 5, 3) when they have OS-level or model-specific
work that a generic reasoning-or-tool-call step genuinely cannot express;
at that point they graduate to their own `DomainAgent` subclass, and this
generic class remains for agents that never need more than this.
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
    """The eight named domain agents from the project mandate, with their
    Phase 2 tool allowlists and reasoning framing. Vision/Automation/
    Earth/Security intentionally have empty tool allowlists until their
    respective phases give them real capabilities to gate — an empty
    allowlist means "reasoning-only for now," not "broken.\""""
    return {
        EventSource.AGENT_DESKTOP: DomainAgentSpec(
            identity=EventSource.AGENT_DESKTOP,
            description="Understands and reasons about desktop application state.",
            allowed_tools=frozenset({"system.list_agents"}),
            system_prompt="You are the Desktop agent. You reason about applications, "
            "windows, and UI state. Respond concisely and factually.",
        ),
        EventSource.AGENT_VISION: DomainAgentSpec(
            identity=EventSource.AGENT_VISION,
            description="Interprets screen/image content (Phase 5).",
            system_prompt="You are the Vision agent, operating in reasoning-only mode "
            "until image analysis tooling lands. Be explicit about this limitation "
            "if the step requires actual image interpretation.",
        ),
        EventSource.AGENT_RESEARCH: DomainAgentSpec(
            identity=EventSource.AGENT_RESEARCH,
            description="Gathers and synthesizes information (web/local search, Phase 4+).",
            system_prompt="You are the Research agent, operating in reasoning-only mode "
            "until search tooling lands. Be explicit about this limitation if the step "
            "requires live information you don't have.",
        ),
        EventSource.AGENT_SECURITY: DomainAgentSpec(
            identity=EventSource.AGENT_SECURITY,
            description="Monitors and reasons about system security posture (Phase 3).",
            system_prompt="You are the Security agent, operating in reasoning-only mode "
            "until monitoring tooling lands in Phase 3.",
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
            description="Geospatial visualization and reasoning (Phase 5, CesiumJS).",
            system_prompt="You are the Earth agent, operating in reasoning-only mode "
            "until geospatial tooling lands in Phase 5.",
        ),
        EventSource.AGENT_AUTOMATION: DomainAgentSpec(
            identity=EventSource.AGENT_AUTOMATION,
            description="Executes desktop automation sequences (Phase 4).",
            system_prompt="You are the Automation agent, operating in reasoning-only mode "
            "until automation tooling lands in Phase 4. Never claim to have performed a "
            "desktop action you cannot actually perform yet.",
        ),
        EventSource.AGENT_DEVELOPER: DomainAgentSpec(
            identity=EventSource.AGENT_DEVELOPER,
            description="Reasons about code and development tasks.",
            allowed_tools=frozenset({"system.list_agents", "system.get_current_time"}),
            system_prompt="You are the Developer agent. You reason about code, "
            "architecture, and development tasks precisely and technically.",
        ),
    }
