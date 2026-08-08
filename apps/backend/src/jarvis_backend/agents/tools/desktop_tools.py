"""Phase 5 desktop intelligence and automation tools.

Read-only desktop inspection is exposed to the Desktop Agent. Mutating
window/input operations are exposed to the Automation Agent and carry the
existing `automation.input` SafetyGate scope.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from jarvis_contracts import EventSource

from ..desktop import InputControllerProtocol, UIInspectorProtocol, WindowManagerProtocol
from ..safety_gate import PermissionScope
from ..tool_registry import ToolRegistry, ToolSpec


def register_desktop_tools(
    registry: ToolRegistry,
    *,
    window_manager: WindowManagerProtocol,
    ui_inspector: UIInspectorProtocol,
    input_controller: InputControllerProtocol,
) -> None:
    """Register Phase 5 desktop inspection and automation tools."""

    registry.register(
        ToolSpec(
            name="desktop.list_windows",
            description="List visible top-level desktop windows with their bounds and state.",
            handler=_make_list_windows_handler(window_manager),
            owner_agent=EventSource.AGENT_DESKTOP,
        )
    )
    registry.register(
        ToolSpec(
            name="desktop.active_window",
            description="Return the currently active desktop window and its bounds.",
            handler=_make_active_window_handler(window_manager),
            owner_agent=EventSource.AGENT_DESKTOP,
        )
    )
    registry.register(
        ToolSpec(
            name="desktop.inspect_ui",
            description="Inspect a native Windows UI Automation tree for a named window.",
            handler=_make_inspect_ui_handler(ui_inspector),
            owner_agent=EventSource.AGENT_DESKTOP,
        )
    )

    automation_scope = PermissionScope.AUTOMATION_INPUT.value
    registry.register(
        ToolSpec(
            name="automation.focus_window",
            description="Focus a desktop window by its exact title.",
            handler=_make_focus_window_handler(window_manager),
            permission_scope=automation_scope,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.move_window",
            description="Move a desktop window to screen coordinates x,y.",
            handler=_make_move_window_handler(window_manager),
            permission_scope=automation_scope,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.resize_window",
            description="Resize a desktop window to the requested width and height.",
            handler=_make_resize_window_handler(window_manager),
            permission_scope=automation_scope,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.click",
            description="Move to a screen coordinate and click it with the selected mouse button.",
            handler=_make_click_handler(input_controller),
            permission_scope=automation_scope,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.type_text",
            description="Type text into the currently focused desktop control.",
            handler=_make_type_text_handler(input_controller),
            permission_scope=automation_scope,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.press_key",
            description="Press one supported keyboard key.",
            handler=_make_press_key_handler(input_controller),
            permission_scope=automation_scope,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.hotkey",
            description="Press a keyboard shortcut containing one to four supported keys.",
            handler=_make_hotkey_handler(input_controller),
            permission_scope=automation_scope,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.scroll",
            description="Scroll the active desktop control by a bounded number of clicks.",
            handler=_make_scroll_handler(input_controller),
            permission_scope=automation_scope,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )


def _make_list_windows_handler(window_manager: WindowManagerProtocol):
    async def handler(_args: dict[str, object]) -> str:
        return json.dumps([asdict(window) for window in window_manager.list_windows()], default=str)

    return handler


def _make_active_window_handler(window_manager: WindowManagerProtocol):
    async def handler(_args: dict[str, object]) -> str:
        window = window_manager.get_active_window()
        if window is None:
            return "No active desktop window is available."
        return json.dumps(asdict(window), default=str)

    return handler


def _make_inspect_ui_handler(ui_inspector: UIInspectorProtocol):
    async def handler(args: dict[str, object]) -> str:
        title = _required_string(args, "title")
        max_depth = _bounded_int(args, "max_depth", default=3, minimum=0, maximum=8)
        elements = ui_inspector.inspect_window(title, max_depth=max_depth)
        return json.dumps([asdict(element) for element in elements], default=str)

    return handler


def _make_focus_window_handler(window_manager: WindowManagerProtocol):
    async def handler(args: dict[str, object]) -> str:
        title = _required_string(args, "title")
        return json.dumps(asdict(window_manager.focus_window(title)), default=str)

    return handler


def _make_move_window_handler(window_manager: WindowManagerProtocol):
    async def handler(args: dict[str, object]) -> str:
        title = _required_string(args, "title")
        x = _bounded_int(args, "x", minimum=-100_000, maximum=100_000)
        y = _bounded_int(args, "y", minimum=-100_000, maximum=100_000)
        return json.dumps(asdict(window_manager.move_window(title, x, y)), default=str)

    return handler


def _make_resize_window_handler(window_manager: WindowManagerProtocol):
    async def handler(args: dict[str, object]) -> str:
        title = _required_string(args, "title")
        width = _bounded_int(args, "width", minimum=100, maximum=10_000)
        height = _bounded_int(args, "height", minimum=100, maximum=10_000)
        return json.dumps(asdict(window_manager.resize_window(title, width, height)), default=str)

    return handler


def _make_click_handler(input_controller: InputControllerProtocol):
    async def handler(args: dict[str, object]) -> str:
        x = _bounded_int(args, "x", minimum=-100_000, maximum=100_000)
        y = _bounded_int(args, "y", minimum=-100_000, maximum=100_000)
        button = str(args.get("button", "left"))
        clicks = _bounded_int(args, "clicks", default=1, minimum=1, maximum=3)
        point = input_controller.click(x, y, button=button, clicks=clicks)
        return f"Clicked {point.x},{point.y} with {button} button ({clicks} click(s))."

    return handler


def _make_type_text_handler(input_controller: InputControllerProtocol):
    async def handler(args: dict[str, object]) -> str:
        text = _required_string(args, "text")
        interval = _bounded_float(args, "interval_s", default=0.0, minimum=0.0, maximum=1.0)
        input_controller.type_text(text, interval_s=interval)
        return f"Typed {len(text)} characters into the focused control."

    return handler


def _make_press_key_handler(input_controller: InputControllerProtocol):
    async def handler(args: dict[str, object]) -> str:
        key = _required_string(args, "key")
        input_controller.press_key(key)
        return f"Pressed key '{key}'."

    return handler


def _make_hotkey_handler(input_controller: InputControllerProtocol):
    async def handler(args: dict[str, object]) -> str:
        raw_keys = args.get("keys")
        if not isinstance(raw_keys, list) or not all(isinstance(key, str) for key in raw_keys):
            raise ValueError("keys must be a list of one to four strings.")
        keys = [str(key) for key in raw_keys]
        input_controller.hotkey(keys)
        return f"Pressed hotkey: {'+'.join(keys)}."

    return handler


def _make_scroll_handler(input_controller: InputControllerProtocol):
    async def handler(args: dict[str, object]) -> str:
        clicks = _bounded_int(args, "clicks", minimum=-100, maximum=100)
        if clicks == 0:
            raise ValueError("clicks must not be zero.")
        input_controller.scroll(clicks)
        return f"Scrolled {clicks} click(s)."

    return handler


def _required_string(args: dict[str, object], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{name}' is required and must be a non-empty string.")
    return value.strip()


def _bounded_int(
    args: dict[str, object],
    name: str,
    *,
    default: int | None = None,
    minimum: int,
    maximum: int,
) -> int:
    value = args.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"'{name}' must be an integer.")
    if value < minimum or value > maximum:
        raise ValueError(f"'{name}' must be between {minimum} and {maximum}.")
    return value


def _bounded_float(
    args: dict[str, object],
    name: str,
    *,
    default: float | None = None,
    minimum: float,
    maximum: float,
) -> float:
    value = args.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"'{name}' must be a number.")
    numeric = float(value)
    if numeric < minimum or numeric > maximum:
        raise ValueError(f"'{name}' must be between {minimum} and {maximum}.")
    return numeric
