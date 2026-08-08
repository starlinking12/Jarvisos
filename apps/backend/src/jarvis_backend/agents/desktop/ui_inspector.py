"""Windows UI Automation inspector backed by pywinauto."""

from __future__ import annotations

import sys
from typing import Any

from .types import Rect, UIElementInfo, UIInspectorProtocol
from .window_manager import DesktopAutomationUnavailableError


class UIInspector(UIInspectorProtocol):
    """Inspect native Windows UI Automation trees without mutating them."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise DesktopAutomationUnavailableError(
                "Phase 5 native UI inspection currently requires Windows."
            )
        try:
            from pywinauto import Desktop
        except ImportError as error:
            raise DesktopAutomationUnavailableError(
                "pywinauto is required for native UI inspection; install the 'automation' extra."
            ) from error
        self._desktop = Desktop(backend="uia")

    def inspect_window(self, title: str, *, max_depth: int = 3) -> list[UIElementInfo]:
        if not title.strip():
            raise ValueError("Window title is required.")
        if max_depth < 0 or max_depth > 8:
            raise ValueError("max_depth must be between 0 and 8.")

        window = self._desktop.window(title=title)
        if not window.exists(timeout=0.5):
            raise LookupError(f"No desktop window found with title '{title}'.")

        elements: list[UIElementInfo] = []
        self._walk(window, elements, depth=0, max_depth=max_depth)
        return elements

    def _walk(self, control: Any, output: list[UIElementInfo], *, depth: int, max_depth: int) -> None:
        if depth > max_depth:
            return

        info = self._to_info(control)
        output.append(info)

        if depth == max_depth:
            return

        try:
            children = control.children()
        except Exception:
            return

        for child in children:
            self._walk(child, output, depth=depth + 1, max_depth=max_depth)

    @staticmethod
    def _to_info(control: Any) -> UIElementInfo:
        rectangle = None
        try:
            rect = control.rectangle()
            rectangle = Rect(
                left=int(rect.left),
                top=int(rect.top),
                width=max(0, int(rect.width())),
                height=max(0, int(rect.height())),
            )
        except Exception:
            pass

        name = ""
        control_type = None
        automation_id = None
        enabled = False
        visible = False
        try:
            name = str(control.window_text() or "")
        except Exception:
            pass
        try:
            control_type = str(control.element_info.control_type or "") or None
        except Exception:
            pass
        try:
            automation_id = str(control.element_info.automation_id or "") or None
        except Exception:
            pass
        try:
            enabled = bool(control.is_enabled())
        except Exception:
            pass
        try:
            visible = bool(control.is_visible())
        except Exception:
            pass

        return UIElementInfo(
            name=name,
            control_type=control_type,
            automation_id=automation_id,
            bounds=rectangle,
            enabled=enabled,
            visible=visible,
        )


PyWinAutoUIInspector = UIInspector
