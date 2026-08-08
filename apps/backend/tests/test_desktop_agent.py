from __future__ import annotations

import uuid

from jarvis_contracts import EventSource

from jarvis_backend.agents.desktop_agent import DesktopAgent
from jarvis_backend.agents.domain_agent import DomainAgentSpec
from jarvis_backend.agents.types import PlanStep
from jarvis_backend.desktop.types import WindowInfo


class FakeWindowManager:
    def get_active_window(self) -> WindowInfo | None:
        return WindowInfo(title="Browser", handle=1, left=0, top=0, width=1200, height=800)


class FakeModelRouter:
    async def complete(self, task_type, messages, *, task_id):
        class Result:
            content = "The active application is the Browser."

        assert any("Browser" in message.content for message in messages)
        return Result()


class FakeToolExecutor:
    async def execute(self, task_id, step):
        raise AssertionError("reasoning test must not invoke a tool")


async def test_desktop_agent_reasoning_includes_active_window() -> None:
    agent = DesktopAgent(
        DomainAgentSpec(
            identity=EventSource.AGENT_DESKTOP,
            description="Desktop",
            system_prompt="Desktop system",
        ),
        model_router=FakeModelRouter(),
        tool_executor=FakeToolExecutor(),
        window_manager=FakeWindowManager(),
    )
    step = PlanStep(
        step_id=uuid.uuid4(),
        description="What application is active?",
        agent=EventSource.AGENT_DESKTOP,
    )

    observation = await agent.handle_step(uuid.uuid4(), step)
    assert observation.success is True
    assert "Browser" in observation.detail
