"""Automation Agent — the Phase 5 desktop input specialist."""

from __future__ import annotations

from jarvis_contracts import EventSource

from .domain_agent import DomainAgent, DomainAgentSpec
from .tool_executor import ToolExecutor
from jarvis_backend.ai import ModelRouter


class AutomationAgent(DomainAgent):
    """Specialized identity for desktop automation.

    The actual safety boundary remains ToolExecutor + SafetyGate. Keeping the
    class thin prevents authorization logic from being duplicated here while
    giving the architecture a stable extension point for future sequencing,
    verification, and rollback behavior.
    """


def automation_agent_spec() -> DomainAgentSpec:
    return DomainAgentSpec(
        identity=EventSource.AGENT_AUTOMATION,
        description="Executes verified desktop automation sequences.",
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
            "You are the Automation agent. You execute desktop actions only through "
            "the tools provided to you. Never claim an action succeeded unless the "
            "tool observation explicitly confirms success. Prefer small, reversible "
            "actions and verify the target window before interacting with it."
        ),
    )
