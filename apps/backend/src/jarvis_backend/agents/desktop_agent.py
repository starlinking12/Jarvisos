"""Bespoke Desktop Agent for Phase 5 desktop-state awareness.

The agent remains inside ADR-0008's middle tier. It delegates all tools to
ToolExecutor and only enriches reasoning-only steps with a verified snapshot
of the current active window; it never performs OS actions directly.
"""

from __future__ import annotations

import uuid

from jarvis_contracts import AiTaskType

from jarvis_backend.ai import ChatMessage, ChatRole, ModelRouter

from .desktop.types import WindowManagerProtocol
from .tool_executor import ToolExecutor
from .types import Observation, PlanStep
from .domain_agent import DomainAgent, DomainAgentSpec


class DesktopAgent(DomainAgent):
    """Desktop-aware DomainAgent with read-only active-window context."""

    def __init__(
        self,
        spec: DomainAgentSpec,
        *,
        model_router: ModelRouter,
        tool_executor: ToolExecutor,
        window_manager: WindowManagerProtocol,
    ) -> None:
        super().__init__(spec, model_router=model_router, tool_executor=tool_executor)
        self._window_manager = window_manager

    async def _reason(self, task_id: uuid.UUID, step: PlanStep) -> Observation:
        active_window = self._window_manager.get_active_window()
        if active_window is None:
            desktop_context = "Current active window: none detected."
        else:
            bounds = active_window.bounds
            desktop_context = (
                f"Current active window: {active_window.title!r}; "
                f"bounds=({bounds.left},{bounds.top},{bounds.width},{bounds.height}); "
                f"minimized={active_window.minimized}; maximized={active_window.maximized}."
            )

        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=self.spec.system_prompt),
            ChatMessage(role=ChatRole.SYSTEM, content=desktop_context),
            ChatMessage(role=ChatRole.USER, content=step.description),
        ]
        result = await self._model_router.complete(
            AiTaskType.REASONING, messages, task_id=task_id
        )
        return Observation(step_id=step.step_id, success=True, detail=result.content)
