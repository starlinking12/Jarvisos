"""Desktop input and window-control tools.

Every mutating operation is explicitly marked with ``automation.input`` so
ToolExecutor/SafetyGate remains the sole authorization choke point. These
handlers perform no permission checks themselves, but they validate tool
arguments before invoking native adapters.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from jarvis_contracts import EventSource

from jarvis_backend.desktop.types import InputController, WindowManager

from ..tool_registry import ToolRegistry, ToolSpec

_AUTOMATION_SCOPE = "automation.input"
_MAX_TYPED_TEXT = 10_000
Handler = Callable[[dict[str, object]], Awaitable[str]]


def register_automation_tools(
    registry: ToolRegistry,
    *,
    window_manager: WindowManager,
    input_controller: InputController,
) -> None:
    """Register high-impact desktop automation capabilities."""
    registry.register(
        ToolSpec(
            name="automation.focus_window",
            description="Focus a desktop window by title substring.",
            handler=_focus_window(window_manager),
            permission_scope=_AUTOMATION_SCOPE,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.minimize_window",
            description="Minimize a desktop window by title substring.",
            handler=_window_action(window_manager, "minimize_window"),
            permission_scope=_AUTOMATION_SCOPE,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.maximize_window",
            description="Maximize a desktop window by title substring.",
            handler=_window_action(window_manager, "maximize_window"),
            permission_scope=_AUTOMATION_SCOPE,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.close_window",
            description="Close a desktop window by title substring.",
            handler=_window_action(window_manager, "close_window"),
            permission_scope=_AUTOMATION_SCOPE,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.mouse_position",
            description="Read the current mouse cursor position.",
            handler=_mouse_position(input_controller),
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.move_mouse",
            description="Move the mouse cursor to screen coordinates.",
            handler=_move_mouse(input_controller),
            permission_scope=_AUTOMATION_SCOPE,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.click",
            description="Click at screen coordinates with a selected mouse button.",
            handler=_click(input_controller),
            permission_scope=_AUTOMATION_SCOPE,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.type_text",
            description="Type text into the currently focused application.",
            handler=_type_text(input_controller),
            permission_scope=_AUTOMATION_SCOPE,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.press_key",
            description="Press one keyboard key in the currently focused application.",
            handler=_press_key(input_controller),
            permission_scope=_AUTOMATION_SCOPE,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.hotkey",
            description="Press a keyboard shortcut such as ctrl+shift+s.",
            handler=_hotkey(input_controller),
            permission_scope=_AUTOMATION_SCOPE,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )
    registry.register(
        ToolSpec(
            name="automation.scroll",
            description="Scroll the currently focused desktop surface.",
            handler=_scroll(input_controller),
            permission_scope=_AUTOMATION_SCOPE,
            owner_agent=EventSource.AGENT_AUTOMATION,
        )
    )


def _focus_window(window_manager: WindowManager) -> Handler:
    async def handler(args: dict[str, object]) -> str:
        title = _required_string(args, "title")
        return _result("focus window", window_manager.focus_window(title), title)

    return handler


def _window_action(window_manager: WindowManager, method_name: str) -> Handler:
    async def handler(args: dict[str, object]) -> str:
        title = _required_string(args, "title")
        action = getattr(window_manager, method_name)
        return _result(method_name.replace("_", " "), action(title), title)

    return handler


def _mouse_position(input_controller: InputController) -> Handler:
    async def handler(args: dict[str, object]) -> str:
        del args
        x, y = input_controller.position()
        return f"Mouse position: x={x}, y={y}."

    return handler


def _move_mouse(input_controller: InputController) -> Handler:
    async def handler(args: dict[str, object]) -> str:
        x = _required_int(args, "x")
        y = _required_int(args, "y")
        duration = _optional_float(args, "duration_s", default=0.0, minimum=0.0)
        input_controller.move(x, y, duration_s=duration)
        return f"Moved mouse to x={x}, y={y}."

    return handler


def _click(input_controller: InputController) -> Handler:
    async def handler(args: dict[str, object]) -> str:
        x = _required_int(args, "x")
        y = _required_int(args, "y")
        button = _optional_button(args, "button", default="left")
        clicks = _optional_int(args, "clicks", default=1, minimum=1, maximum=3)
        input_controller.click(x, y, button=button, clicks=clicks)
        return f"Clicked {button} at x={x}, y={y} ({clicks} click(s))."

    return handler


def _type_text(input_controller: InputController) -> Handler:
    async def handler(args: dict[str, object]) -> str:
        text = _required_string(args, "text")
        if len(text) > _MAX_TYPED_TEXT:
            raise ValueError(f"'text' exceeds the {_MAX_TYPED_TEXT}-character limit")
        interval = _optional_float(args, "interval_s", default=0.0, minimum=0.0)
        input_controller.type_text(text, interval_s=interval)
        return f"Typed {len(text)} characters."

    return handler


def _press_key(input_controller: InputController) -> Handler:
    async def handler(args: dict[str, object]) -> str:
        key = _required_string(args, "key")
        input_controller.press(key)
        return f"Pressed key '{key}'."

    return handler


def _hotkey(input_controller: InputController) -> Handler:
    async def handler(args: dict[str, object]) -> str:
        raw_keys = args.get("keys")
        if (
            not isinstance(raw_keys, list)
            or not raw_keys
            or any(not isinstance(key, str) for key in raw_keys)
        ):
            raise ValueError("'keys' must be a non-empty list of strings")
        keys = [key.strip() for key in raw_keys]
        if any(not key for key in keys):
            raise ValueError("'keys' cannot contain empty values")
        input_controller.hotkey(*keys)
        return f"Pressed hotkey: {'+'.join(keys)}."

    return handler


def _scroll(input_controller: InputController) -> Handler:
    async def handler(args: dict[str, object]) -> str:
        amount = _required_int(args, "amount")
        input_controller.scroll(amount)
        return f"Scrolled by {amount}."

    return handler


def _required_string(args: dict[str, object], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{name}' must be a non-empty string")
    return value.strip()


def _required_int(args: dict[str, object], name: str) -> int:
    value = args.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"'{name}' must be an integer")
    return value


def _optional_int(
    args: dict[str, object],
    name: str,
    *,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = args.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"'{name}' must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"'{name}' must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"'{name}' must be <= {maximum}")
    return value


def _optional_float(
    args: dict[str, object],
    name: str,
    *,
    default: float,
    minimum: float | None = None,
) -> float:
    value = args.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"'{name}' must be a number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"'{name}' must be >= {minimum}")
    return result


def _optional_button(args: dict[str, object], name: str, *, default: str) -> str:
    value = args.get(name, default)
    if not isinstance(value, str) or value not in {"left", "middle", "right"}:
        raise ValueError("'button' must be one of: left, middle, right")
    return value


def _result(action: str, success: bool, title: str) -> str:
    if success:
        return f"Successfully requested to {action} '{title}'."
    return f"Could not {action} '{title}': window not found or operation failed."
