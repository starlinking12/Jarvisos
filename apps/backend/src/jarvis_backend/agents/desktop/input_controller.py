"""OS input synthesis provider backed by pyautogui."""

from __future__ import annotations

import sys
from typing import Any

from .types import InputControllerProtocol, Point
from .window_manager import DesktopAutomationUnavailableError


class InputController(InputControllerProtocol):
    """pyautogui-backed mouse and keyboard controller."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise DesktopAutomationUnavailableError(
                "Phase 5 desktop input currently requires Windows."
            )
        try:
            import pyautogui
        except ImportError as error:
            raise DesktopAutomationUnavailableError(
                "pyautogui is required for desktop input; install the 'automation' extra."
            ) from error
        self._pyautogui = pyautogui

    def move_mouse(self, x: int, y: int) -> Point:
        self._validate_coordinate(x, y)
        self._pyautogui.moveTo(x, y)
        return Point(x=x, y=y)

    def click(self, x: int, y: int, *, button: str = "left", clicks: int = 1) -> Point:
        self._validate_coordinate(x, y)
        if button not in {"left", "middle", "right"}:
            raise ValueError("button must be 'left', 'middle', or 'right'.")
        if clicks < 1 or clicks > 3:
            raise ValueError("clicks must be between 1 and 3.")
        self._pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        return Point(x=x, y=y)

    def type_text(self, text: str, *, interval_s: float = 0.0) -> None:
        if not isinstance(text, str) or not text:
            raise ValueError("Text to type must be a non-empty string.")
        if len(text) > 10_000:
            raise ValueError("Text to type is limited to 10,000 characters per action.")
        if interval_s < 0 or interval_s > 1:
            raise ValueError("interval_s must be between 0 and 1 second.")
        self._pyautogui.write(text, interval=interval_s)

    def press_key(self, key: str) -> None:
        normalized = key.strip().lower()
        if normalized not in _ALLOWED_KEYS:
            raise ValueError(f"Unsupported key '{key}'.")
        self._pyautogui.press(normalized)

    def hotkey(self, keys: list[str]) -> None:
        if not keys or len(keys) > 4:
            raise ValueError("A hotkey must contain between 1 and 4 keys.")
        normalized = [key.strip().lower() for key in keys]
        invalid = [key for key in normalized if key not in _ALLOWED_KEYS]
        if invalid:
            raise ValueError(f"Unsupported hotkey key(s): {', '.join(invalid)}")
        self._pyautogui.hotkey(*normalized)

    def scroll(self, clicks: int) -> None:
        if clicks == 0 or abs(clicks) > 100:
            raise ValueError("scroll clicks must be between -100 and 100, excluding zero.")
        self._pyautogui.scroll(clicks)

    @staticmethod
    def _validate_coordinate(x: int, y: int) -> None:
        if not isinstance(x, int) or not isinstance(y, int):
            raise ValueError("Mouse coordinates must be integers.")
        if abs(x) > 100_000 or abs(y) > 100_000:
            raise ValueError("Mouse coordinates are outside the supported range.")


PyAutoGuiInputController = InputController

_ALLOWED_KEYS = {
    "alt",
    "backspace",
    "ctrl",
    "delete",
    "down",
    "end",
    "enter",
    "esc",
    "home",
    "left",
    "pagedown",
    "pageup",
    "right",
    "shift",
    "space",
    "tab",
    "up",
    "win",
    *{f"f{i}" for i in range(1, 13)},
    *{str(i) for i in range(10)},
    *list("abcdefghijklmnopqrstuvwxyz"),
    *list("0123456789"),
    "-",
    "=",
    ",",
    ".",
    "/",
    ";",
    "'",
    "[",
    "]",
    "\\",
    "`",
}
