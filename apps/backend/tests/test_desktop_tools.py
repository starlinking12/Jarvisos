from __future__ import annotations

import json

import pytest

from jarvis_backend.agents.desktop.types import Point, Rect, UIElementInfo, WindowInfo
from jarvis_backend.agents.tools.desktop_tools import register_desktop_tools
from jarvis_backend.agents.tool_registry import ToolRegistry


class FakeWindowManager:
    def __init__(self) -> None:
        self.windows = [
            WindowInfo(
                title="Editor",
                handle=101,
                bounds=Rect(left=10, top=20, width=800, height=600),
                active=True,
            )
        ]

    def list_windows(self) -> list[WindowInfo]:
        return self.windows

    def get_active_window(self) -> WindowInfo | None:
        return self.windows[0]

    def focus_window(self, title: str) -> WindowInfo:
        assert title == "Editor"
        return self.windows[0]

    def move_window(self, title: str, x: int, y: int) -> WindowInfo:
        assert title == "Editor"
        return WindowInfo(
            title="Editor",
            handle=101,
            bounds=Rect(left=x, top=y, width=800, height=600),
            active=True,
        )

    def resize_window(self, title: str, width: int, height: int) -> WindowInfo:
        assert title == "Editor"
        return WindowInfo(
            title="Editor",
            handle=101,
            bounds=Rect(left=10, top=20, width=width, height=height),
            active=True,
        )


class FakeUIInspector:
    def inspect_window(self, title: str, *, max_depth: int = 3) -> list[UIElementInfo]:
        assert title == "Editor"
        return [
            UIElementInfo(
                name="Save",
                control_type="Button",
                automation_id="save",
                bounds=Rect(left=20, top=30, width=80, height=30),
                enabled=True,
                visible=True,
            )
        ]


class FakeInputController:
    def move_mouse(self, x: int, y: int) -> Point:
        return Point(x=x, y=y)

    def click(self, x: int, y: int, *, button: str = "left", clicks: int = 1) -> Point:
        return Point(x=x, y=y)

    def type_text(self, text: str, *, interval_s: float = 0.0) -> None:
        self.last_text = text

    def press_key(self, key: str) -> None:
        self.last_key = key

    def hotkey(self, keys: list[str]) -> None:
        self.last_hotkey = keys

    def scroll(self, clicks: int) -> None:
        self.last_scroll = clicks


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_desktop_tools(
        registry,
        window_manager=FakeWindowManager(),
        ui_inspector=FakeUIInspector(),
        input_controller=FakeInputController(),
    )
    return registry


def test_phase5_tool_registration_and_security_metadata() -> None:
    registry = _registry()

    desktop = registry.get("desktop.list_windows")
    automation = registry.get("automation.click")

    assert desktop is not None
    assert desktop.owner_agent.value == "agent.desktop"
    assert desktop.permission_scope is None

    assert automation is not None
    assert automation.owner_agent.value == "agent.automation"
    assert automation.permission_scope == "automation.input"


@pytest.mark.asyncio
async def test_read_only_desktop_tools_return_verified_data() -> None:
    registry = _registry()

    windows = await registry.get("desktop.list_windows").handler({})  # type: ignore[union-attr]
    active = await registry.get("desktop.active_window").handler({})  # type: ignore[union-attr]
    ui = await registry.get("desktop.inspect_ui").handler({"title": "Editor"})  # type: ignore[union-attr]

    assert json.loads(windows)[0]["title"] == "Editor"
    assert json.loads(active)["active"] is True
    assert json.loads(ui)[0]["name"] == "Save"


@pytest.mark.asyncio
async def test_automation_tools_validate_inputs() -> None:
    registry = _registry()
    click = registry.get("automation.click")
    type_text = registry.get("automation.type_text")

    with pytest.raises(ValueError, match="'x' must be an integer"):
        await click.handler({"x": "bad", "y": 10})  # type: ignore[union-attr]

    with pytest.raises(ValueError, match="'text' is required"):
        await type_text.handler({})  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_automation_click_returns_action_confirmation() -> None:
    registry = _registry()
    click = registry.get("automation.click")

    result = await click.handler({"x": 100, "y": 200, "button": "left", "clicks": 2})  # type: ignore[union-attr]

    assert "100,200" in result
    assert "2 click" in result
