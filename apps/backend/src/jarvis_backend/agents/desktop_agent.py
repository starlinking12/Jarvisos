"""Desktop Agent — Phase 5 specialization of DomainAgent."""

from __future__ import annotations

import uuid

from jarvis_contracts import AiTaskType

from jarvis_backend.ai import ChatMessage, ChatRole, ModelRouter
from jarvis_backend.desktop.types import WindowManager

from .domain_agent import DomainAgent, DomainAgentSpec
from .tool_executor import ToolExecutor
from .types import Observation, PlanStep


class DesktopAgent(DomainAgent):
    """Reason about desktop state with verified live window context."""

    def __init__(
        self,
        spec: DomainAgentSpec,
        *,
        model_router: ModelRouter,
        tool_executor: ToolExecutor,
        window_manager: WindowManager,
    ) -> None:
        super().__init__(spec, model_router=model_router, tool_executor=tool_executor)
        self._window_manager = window_manager

    async def _reason(self, task_id: uuid.UUID, step: PlanStep) -> Observation:
        try:
            active_window = self._window_manager.get_active_window()
            desktop_context = (
                f"Active window: {active_window.title}"
                if active_window is not None
                else "Active window: none detected"
            )
        except Exception as error:  # noqa: BLE001 - OS adapter failures must not crash reasoning
            desktop_context = f"Active window: unavailable ({error})"

        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=self.spec.system_prompt),
            ChatMessage(role=ChatRole.SYSTEM, content=desktop_context),
            ChatMessage(role=ChatRole.USER, content=step.description),
        ]
        result = await self._model_router.complete(
            AiTaskType.REASONING, messages, task_id=task_id
        )
        return Observation(step_id=step.step_id, success=True, detail=result.content)
