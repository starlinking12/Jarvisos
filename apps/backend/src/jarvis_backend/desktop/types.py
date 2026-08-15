"""Platform-neutral types and protocols for desktop automation.

The rest of the backend depends on these abstractions rather than directly on
pyautogui/pygetwindow. That keeps OS integration replaceable and makes the
agent/tool layer straightforward to test with fakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True, frozen=True)
class WindowInfo:
    """A normalized snapshot of a desktop window."""

    title: str
    handle: int | None = None
    left: int | None = None
    top: int | None = None
    width: int | None = None
    height: int | None = None
    minimized: bool = False
    maximized: bool = False


class WindowManager(Protocol):
    """Platform abstraction for querying and manipulating windows."""

    def list_windows(self) -> list[WindowInfo]: ...

    def get_active_window(self) -> WindowInfo | None: ...

    def find_window(self, title: str) -> WindowInfo | None: ...

    def focus_window(self, title: str) -> bool: ...

    def minimize_window(self, title: str) -> bool: ...

    def maximize_window(self, title: str) -> bool: ...

    def close_window(self, title: str) -> bool: ...


class InputController(Protocol):
    """Platform abstraction for synthetic mouse/keyboard input."""

    def position(self) -> tuple[int, int]: ...

    def move(self, x: int, y: int, *, duration_s: float = 0.0) -> None: ...

    def click(self, x: int, y: int, *, button: str = "left", clicks: int = 1) -> None: ...

    def type_text(self, text: str, *, interval_s: float = 0.0) -> None: ...

    def press(self, key: str) -> None: ...

    def hotkey(self, *keys: str) -> None: ...

    def scroll(self, amount: int) -> None: ...
