"""pygetwindow-backed window management.

The dependency is optional at import time so the backend remains usable on
machines where desktop automation dependencies are not installed. The
composition root is responsible for deciding whether to construct this
adapter; unit tests can inject a fake WindowManager instead.
"""

from __future__ import annotations

from typing import Any

from .types import WindowInfo


class DesktopDependencyUnavailable(RuntimeError):
    """Raised when the native desktop adapter is requested without its dependency."""


class PyGetWindowManager:
    """WindowManager implementation backed by pygetwindow."""

    def __init__(self) -> None:
        try:
            import pygetwindow as gw
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise DesktopDependencyUnavailable(
                "pygetwindow is required for desktop window management; "
                "install the backend's automation extra"
            ) from exc
        self._gw = gw

    def list_windows(self) -> list[WindowInfo]:
        windows: list[WindowInfo] = []
        for window in self._gw.getAllWindows():
            info = self._to_info(window)
            if info.title.strip():
                windows.append(info)
        return windows

    def get_active_window(self) -> WindowInfo | None:
        window = self._gw.getActiveWindow()
        return self._to_info(window) if window is not None else None

    def find_window(self, title: str) -> WindowInfo | None:
        needle = title.casefold().strip()
        if not needle:
            return None
        for window in self._gw.getAllWindows():
            if needle in str(getattr(window, "title", "")).casefold():
                return self._to_info(window)
        return None

    def focus_window(self, title: str) -> bool:
        window = self._resolve(title)
        if window is None:
            return False
        try:
            if bool(getattr(window, "isMinimized", False)):
                window.restore()
            window.activate()
            return True
        except Exception:
            return False

    def minimize_window(self, title: str) -> bool:
        window = self._resolve(title)
        if window is None:
            return False
        try:
            window.minimize()
            return True
        except Exception:
            return False

    def maximize_window(self, title: str) -> bool:
        window = self._resolve(title)
        if window is None:
            return False
        try:
            window.maximize()
            return True
        except Exception:
            return False

    def close_window(self, title: str) -> bool:
        window = self._resolve(title)
        if window is None:
            return False
        try:
            window.close()
            return True
        except Exception:
            return False

    def _resolve(self, title: str) -> Any | None:
        needle = title.casefold().strip()
        if not needle:
            return None
        for window in self._gw.getAllWindows():
            if needle in str(getattr(window, "title", "")).casefold():
                return window
        return None

    @staticmethod
    def _to_info(window: Any) -> WindowInfo:
        return WindowInfo(
            title=str(getattr(window, "title", "")),
            handle=getattr(window, "_hWnd", None),
            left=_safe_int(getattr(window, "left", None)),
            top=_safe_int(getattr(window, "top", None)),
            width=_safe_int(getattr(window, "width", None)),
            height=_safe_int(getattr(window, "height", None)),
            minimized=bool(getattr(window, "isMinimized", False)),
            maximized=bool(getattr(window, "isMaximized", False)),
        )


def _safe_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
