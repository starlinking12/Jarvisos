"""Desktop intelligence and automation providers for JARVIS OS Phase 5."""

from .input_controller import InputController, PyAutoGuiInputController
from .types import InputControllerProtocol, Point, Rect, UIElementInfo, UIInspectorProtocol, WindowInfo, WindowManagerProtocol
from .ui_inspector import PyWinAutoUIInspector, UIInspector
from .window_manager import PyGetWindowManager, WindowManager

__all__ = [
    "InputController",
    "InputControllerProtocol",
    "Point",
    "PyAutoGuiInputController",
    "PyGetWindowManager",
    "PyWinAutoUIInspector",
    "Rect",
    "UIElementInfo",
    "UIInspector",
    "UIInspectorProtocol",
    "WindowInfo",
    "WindowManager",
    "WindowManagerProtocol",
]
