"""pyautogui-backed synthetic input adapter."""

from __future__ import annotations

from .types import InputController


class AutomationDependencyUnavailable(RuntimeError):
    """Raised when synthetic input is requested without pyautogui."""


class PyAutoGUIInputController:
    """InputController implementation backed by pyautogui."""

    def __init__(self) -> None:
        try:
            import pyautogui
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise AutomationDependencyUnavailable(
                "pyautogui is required for desktop input automation; "
                "install the backend's automation extra"
            ) from exc
        self._pyautogui = pyautogui

    def position(self) -> tuple[int, int]:
        point = self._pyautogui.position()
        return int(point.x), int(point.y)

    def move(self, x: int, y: int, *, duration_s: float = 0.0) -> None:
        self._pyautogui.moveTo(x, y, duration=max(0.0, duration_s))

    def click(self, x: int, y: int, *, button: str = "left", clicks: int = 1) -> None:
        if button not in {"left", "middle", "right"}:
            raise ValueError("button must be one of: left, middle, right")
        if clicks < 1 or clicks > 3:
            raise ValueError("clicks must be between 1 and 3")
        self._pyautogui.click(x=x, y=y, clicks=clicks, button=button)

    def type_text(self, text: str, *, interval_s: float = 0.0) -> None:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        self._pyautogui.write(text, interval=max(0.0, interval_s))

    def press(self, key: str) -> None:
        if not key.strip():
            raise ValueError("key must not be empty")
        self._pyautogui.press(key)

    def hotkey(self, *keys: str) -> None:
        if not keys or any(not key.strip() for key in keys):
            raise ValueError("hotkey requires one or more non-empty keys")
        self._pyautogui.hotkey(*keys)

    def scroll(self, amount: int) -> None:
        if amount == 0:
            return
        self._pyautogui.scroll(amount)
