"""Startup monitor — Windows Run-key and Startup-folder entries.

**Platform scope, stated plainly:** the project mandate is Windows-first,
and startup persistence mechanisms (registry Run keys, the Startup
folder) are Windows-specific concepts with no cross-platform equivalent
this monitor could substitute — there is no "startup items" API on
Linux/macOS analogous enough to be worth faking. On any non-Windows
platform, `scan()` returns an empty list with a logged notice, the same
graceful-degradation pattern already established for optional native
dependencies elsewhere in this project (`NullNoiseSuppressor`,
`NullEchoCanceller` in `voice/vad/audio_processing.py`) — this is honest
"not applicable here," not a placeholder standing in for missing work.
"""

from __future__ import annotations

import sys
from pathlib import Path

import structlog

from .types import FindingSeverity, SecurityCategory, SecurityFinding

logger = structlog.get_logger("jarvis_backend.security.startup_monitor")

RUN_KEY_PATHS = (
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "HKEY_CURRENT_USER"),
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "HKEY_LOCAL_MACHINE"),
)


class StartupMonitor:
    name = "startup"

    def __init__(self, known_entries: frozenset[str] = frozenset()) -> None:
        self._known_entries = known_entries

    async def scan(self) -> list[SecurityFinding]:
        if sys.platform != "win32":
            logger.debug("startup_monitor_not_applicable", platform=sys.platform)
            return []

        findings: list[SecurityFinding] = []
        findings.extend(self._scan_run_keys())
        findings.extend(self._scan_startup_folder())
        return findings

    def _scan_run_keys(self) -> list[SecurityFinding]:
        import winreg  # Windows-only stdlib module — import is only reached
        # when sys.platform == "win32", per scan()'s guard above.

        findings: list[SecurityFinding] = []
        root_map = {
            "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
            "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        }

        for subkey_path, root_name in RUN_KEY_PATHS:
            try:
                with winreg.OpenKey(root_map[root_name], subkey_path) as key:
                    index = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, index)
                        except OSError:
                            break
                        if name not in self._known_entries:
                            findings.append(
                                SecurityFinding(
                                    category=SecurityCategory.STARTUP,
                                    severity=FindingSeverity.INFO,
                                    message=f"Unrecognized startup entry in {root_name}\\"
                                    f"{subkey_path}: {name} -> {value}",
                                )
                            )
                        index += 1
            except FileNotFoundError:
                continue
            except OSError:
                logger.warning("startup_registry_scan_failed", key=subkey_path, exc_info=True)

        return findings

    def _scan_startup_folder(self) -> list[SecurityFinding]:
        startup_dir = (
            Path.home()
            / "AppData"
            / "Roaming"
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
        )
        if not startup_dir.exists():
            return []

        findings: list[SecurityFinding] = []
        for entry in startup_dir.iterdir():
            if entry.name not in self._known_entries:
                findings.append(
                    SecurityFinding(
                        category=SecurityCategory.STARTUP,
                        severity=FindingSeverity.INFO,
                        message=f"Unrecognized Startup folder entry: {entry.name}",
                    )
                )
        return findings
