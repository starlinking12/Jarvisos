"""Desktop intelligence and automation adapters."""

from .input_controller import AutomationDependencyUnavailable, PyAutoGUIInputController
from .types import InputController, WindowInfo, WindowManager
from .window_manager import DesktopDependencyUnavailable, PyGetWindowManager

__all__ = [
    "AutomationDependencyUnavailable",
    "DesktopDependencyUnavailable",
    "InputController",
    "PyAutoGUIInputController",
    "PyGetWindowManager",
    "WindowInfo",
    "WindowManager",
]
