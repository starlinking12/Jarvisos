"""Top-level desktop window provider backed by pygetwindow.

The provider is intentionally Windows-first but keeps the interface small
and platform-neutral. Unsupported platforms or missing optional dependencies
fail explicitly rather than pretending desktop control is available.
"""

from __future__ import annotations

import sys
from typing import Any

from .types import Rect, WindowInfo, WindowManagerProtocol


class DesktopAutomationUnavailableError(RuntimeError):
    """Raised when the selected desktop backend cannot run on this host."""


class WindowManager(WindowManagerProtocol):
    """pygetwindow-backed top-level window manager."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise DesktopAutomationUnavailableError(
                "Phase 5 desktop window control currently requires Windows."
            )
        try:
            import pygetwindow as gw
        except ImportError as error:
            raise DesktopAutomationUnavailableError(
                "pygetwindow is required for desktop window control; install the 'automation' extra."
            ) from error
        self._gw = gw

    def list_windows(self) -> list[WindowInfo]:
        windows: list[WindowInfo] = []
        for window in self._gw.getAllWindows():
            title = str(getattr(window, "title", "") or "").strip()
            if not title:
                continue
            windows.append(self._to_info(window))
        return windows

    def get_active_window(self) -> WindowInfo | None:
        window = self._gw.getActiveWindow()
        if window is None:
            return None
        return self._to_info(window, active=True)

    def focus_window(self, title: str) -> WindowInfo:
        window = self._find(title)
        if getattr(window, "isMinimized", False):
            window.restore()
        window.activate()
        return self._to_info(window, active=True)

    def move_window(self, title: str, x: int, y: int) -> WindowInfo:
        window = self._find(title)
        window.moveTo(x, y)
        return self._to_info(window)

    def resize_window(self, title: str, width: int, height: int) -> WindowInfo:
        if width <= 0 or height <= 0:
            raise ValueError("Window width and height must be positive.")
        window = self._find(title)
        window.resizeTo(width, height)
        return self._to_info(window)

    def _find(self, title: str) -> Any:
        normalized = title.strip().casefold()
        if not normalized:
            raise ValueError("Window title is required.")
        for window in self._gw.getAllWindows():
            candidate = str(getattr(window, "title", "") or "").strip()
            if candidate.casefold() == normalized:
                return window
        raise LookupError(f"No desktop window found with title '{title}'.")

    @staticmethod
    def _to_info(window: Any, *, active: bool = False) -> WindowInfo:
        return WindowInfo(
            title=str(getattr(window, "title", "") or ""),
            handle=getattr(window, "_hWnd", None),
            bounds=Rect(
                left=int(getattr(window, "left", 0)),
                top=int(getattr(window, "top", 0)),
                width=max(0, int(getattr(window, "width", 0))),
                height=max(0, int(getattr(window, "height", 0))),
            ),
            active=active or bool(getattr(window, "isActive", False)),
            minimized=bool(getattr(window, "isMinimized", False)),
            maximized=bool(getattr(window, "isMaximized", False)),
        )


PyGetWindowManager = WindowManager
