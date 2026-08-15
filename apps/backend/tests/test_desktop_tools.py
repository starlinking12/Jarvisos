from __future__ import annotations

import pytest

from jarvis_backend.agents.tools.automation_tools import register_automation_tools
from jarvis_backend.agents.tools.desktop_tools import register_desktop_tools
from jarvis_backend.agents.tool_registry import ToolRegistry
from jarvis_backend.desktop.types import WindowInfo


class FakeWindowManager:
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []

    def list_windows(self) -> list[WindowInfo]:
        return [WindowInfo(title="Editor", handle=1, left=10, top=20, width=800, height=600)]

    def get_active_window(self) -> WindowInfo | None:
        return WindowInfo(title="Editor", handle=1, left=10, top=20, width=800, height=600)

    def find_window(self, title: str) -> WindowInfo | None:
        return self.get_active_window() if title.lower() in "editor" else None

    def focus_window(self, title: str) -> bool:
        self.actions.append(("focus", title))
        return title.lower() == "editor"

    def minimize_window(self, title: str) -> bool:
        self.actions.append(("minimize", title))
        return title.lower() == "editor"

    def maximize_window(self, title: str) -> bool:
        self.actions.append(("maximize", title))
        return title.lower() == "editor"

    def close_window(self, title: str) -> bool:
        self.actions.append(("close", title))
        return title.lower() == "editor"


class FakeInputController:
    def __init__(self) -> None:
        self.actions: list[tuple[str, object]] = []

    def position(self) -> tuple[int, int]:
        return (100, 200)

    def move(self, x: int, y: int, *, duration_s: float = 0.0) -> None:
        self.actions.append(("move", (x, y, duration_s)))

    def click(self, x: int, y: int, *, button: str = "left", clicks: int = 1) -> None:
        self.actions.append(("click", (x, y, button, clicks)))

    def type_text(self, text: str, *, interval_s: float = 0.0) -> None:
        self.actions.append(("type", (text, interval_s)))

    def press(self, key: str) -> None:
        self.actions.append(("press", key))

    def hotkey(self, *keys: str) -> None:
        self.actions.append(("hotkey", keys))

    def scroll(self, amount: int) -> None:
        self.actions.append(("scroll", amount))


def test_desktop_tools_are_read_only() -> None:
    registry = ToolRegistry()
    register_desktop_tools(registry, FakeWindowManager())

    assert registry.get("desktop.list_windows") is not None
    assert registry.get("desktop.active_window") is not None
    assert registry.get("desktop.list_windows").permission_scope is None


def test_automation_tools_are_gated() -> None:
    registry = ToolRegistry()
    register_automation_tools(
        registry,
        window_manager=FakeWindowManager(),
        input_controller=FakeInputController(),
    )

    for name in (
        "automation.focus_window",
        "automation.click",
        "automation.type_text",
        "automation.hotkey",
    ):
        assert registry.get(name).permission_scope == "automation.input"
        assert registry.get(name).owner_agent is not None

    assert registry.get("automation.mouse_position").permission_scope is None


@pytest.mark.asyncio
async def test_click_handler_uses_injected_controller() -> None:
    registry = ToolRegistry()
    controller = FakeInputController()
    register_automation_tools(
        registry,
        window_manager=FakeWindowManager(),
        input_controller=controller,
    )

    result = await registry.get("automation.click").handler(
        {"x": 10, "y": 20, "button": "right", "clicks": 2}
    )

    assert "Clicked right" in result
    assert controller.actions == [("click", (10, 20, "right", 2))]


@pytest.mark.asyncio
async def test_click_handler_rejects_invalid_button_and_click_count() -> None:
    registry = ToolRegistry()
    register_automation_tools(
        registry,
        window_manager=FakeWindowManager(),
        input_controller=FakeInputController(),
    )
    handler = registry.get("automation.click").handler

    with pytest.raises(ValueError, match="button"):
        await handler({"x": 10, "y": 20, "button": "invalid"})

    with pytest.raises(ValueError, match="clicks"):
        await handler({"x": 10, "y": 20, "clicks": 4})


@pytest.mark.asyncio
async def test_type_text_rejects_missing_text_and_oversized_text() -> None:
    registry = ToolRegistry()
    register_automation_tools(
        registry,
        window_manager=FakeWindowManager(),
        input_controller=FakeInputController(),
    )
    handler = registry.get("automation.type_text").handler

    with pytest.raises(ValueError, match="text"):
        await handler({})

    with pytest.raises(ValueError, match="character limit"):
        await handler({"text": "x" * 10_001})
