"""Protocol and value types for desktop intelligence and automation.

The agent layer depends on these structural interfaces rather than concrete
OS libraries. This keeps the orchestration path testable without a desktop,
while the concrete providers remain replaceable as platform support grows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True, frozen=True)
class Point:
    x: int
    y: int


@dataclass(slots=True, frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


@dataclass(slots=True, frozen=True)
class WindowInfo:
    title: str
    handle: int | None
    bounds: Rect
    active: bool = False
    minimized: bool = False
    maximized: bool = False


@dataclass(slots=True, frozen=True)
class UIElementInfo:
    name: str
    control_type: str | None
    automation_id: str | None
    bounds: Rect | None
    enabled: bool
    visible: bool


class WindowManagerProtocol(Protocol):
    """Read and mutate top-level desktop window state."""

    def list_windows(self) -> list[WindowInfo]: ...

    def get_active_window(self) -> WindowInfo | None: ...

    def focus_window(self, title: str) -> WindowInfo: ...

    def move_window(self, title: str, x: int, y: int) -> WindowInfo: ...

    def resize_window(self, title: str, width: int, height: int) -> WindowInfo: ...


class InputControllerProtocol(Protocol):
    """OS input synthesis. Every mutating operation is SafetyGate-gated."""

    def move_mouse(self, x: int, y: int) -> Point: ...

    def click(self, x: int, y: int, *, button: str = "left", clicks: int = 1) -> Point: ...

    def type_text(self, text: str, *, interval_s: float = 0.0) -> None: ...

    def press_key(self, key: str) -> None: ...

    def hotkey(self, keys: list[str]) -> None: ...

    def scroll(self, clicks: int) -> None: ...


class UIInspectorProtocol(Protocol):
    """Inspect native UI Automation trees without mutating application state."""

    def inspect_window(self, title: str, *, max_depth: int = 3) -> list[UIElementInfo]: ...
