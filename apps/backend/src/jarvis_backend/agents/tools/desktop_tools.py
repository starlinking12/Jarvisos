"""Read-only desktop observation tools."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from jarvis_contracts import EventSource

from jarvis_backend.desktop.types import WindowInfo, WindowManager

from ..tool_registry import ToolRegistry, ToolSpec

Handler = Callable[[dict[str, object]], Awaitable[str]]


def register_desktop_tools(registry: ToolRegistry, window_manager: WindowManager) -> None:
    """Register read-only desktop tools for the Desktop agent."""
    registry.register(
        ToolSpec(
            name="desktop.list_windows",
            description="List currently visible desktop windows and their bounds.",
            handler=_list_windows(window_manager),
            owner_agent=EventSource.AGENT_DESKTOP,
        )
    )
    registry.register(
        ToolSpec(
            name="desktop.active_window",
            description="Inspect the currently active desktop window.",
            handler=_active_window(window_manager),
            owner_agent=EventSource.AGENT_DESKTOP,
        )
    )


def _list_windows(window_manager: WindowManager) -> Handler:
    async def handler(args: dict[str, object]) -> str:
        del args
        windows = window_manager.list_windows()
        if not windows:
            return "No titled desktop windows are currently available."
        lines = [f"{index}. {_format_window(window)}" for index, window in enumerate(windows, 1)]
        return "Open desktop windows:\n" + "\n".join(lines)

    return handler


def _active_window(window_manager: WindowManager) -> Handler:
    async def handler(args: dict[str, object]) -> str:
        del args
        window = window_manager.get_active_window()
        if window is None:
            return "No active desktop window was detected."
        return f"Active window: {_format_window(window)}"

    return handler


def _format_window(window: WindowInfo) -> str:
    bounds = "unknown bounds"
    if None not in (window.left, window.top, window.width, window.height):
        bounds = f"x={window.left}, y={window.top}, w={window.width}, h={window.height}"
    state: list[str] = []
    if window.minimized:
        state.append("minimized")
    if window.maximized:
        state.append("maximized")
    state_text = f" ({', '.join(state)})" if state else ""
    return f"{window.title!r} [{bounds}]{state_text}"
