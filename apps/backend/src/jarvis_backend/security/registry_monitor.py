"""Registry monitor — watches a configurable set of security-relevant
Windows registry keys (beyond the Run keys `StartupMonitor` already
covers — e.g. Winlogon shell/userinit, image file execution options
often abused for persistence) for unexpected changes between scans.

Same platform posture as `StartupMonitor`: Windows-only concept, honest
no-op elsewhere — see that module's docstring for the full rationale,
not repeated here.
"""

from __future__ import annotations

import sys
from typing import Any

import structlog

from .types import FindingSeverity, SecurityCategory, SecurityFinding

logger = structlog.get_logger("jarvis_backend.security.registry_monitor")

DEFAULT_WATCHED_KEYS: tuple[tuple[str, str], ...] = (
    (r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon", "HKEY_LOCAL_MACHINE"),
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders", "HKEY_CURRENT_USER"),
)


class RegistryMonitor:
    name = "registry"

    def __init__(self, watched_keys: tuple[tuple[str, str], ...] = DEFAULT_WATCHED_KEYS) -> None:
        self._watched_keys = watched_keys
        self._last_snapshot: dict[str, dict[str, Any]] = {}

    async def scan(self) -> list[SecurityFinding]:
        if sys.platform != "win32":
            logger.debug("registry_monitor_not_applicable", platform=sys.platform)
            return []

        import winreg

        root_map = {
            "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
            "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        }
        findings: list[SecurityFinding] = []

        for subkey_path, root_name in self._watched_keys:
            key_id = f"{root_name}\\{subkey_path}"
            current: dict[str, Any] = {}
            try:
                with winreg.OpenKey(root_map[root_name], subkey_path) as key:
                    index = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, index)
                        except OSError:
                            break
                        current[name] = value
                        index += 1
            except FileNotFoundError:
                continue
            except OSError:
                logger.warning("registry_scan_failed", key=key_id, exc_info=True)
                continue

            previous = self._last_snapshot.get(key_id)
            if previous is not None and previous != current:
                changed = {k: v for k, v in current.items() if previous.get(k) != v}
                findings.append(
                    SecurityFinding(
                        category=SecurityCategory.REGISTRY,
                        severity=FindingSeverity.WARNING,
                        message=f"Registry key changed: {key_id} — modified values: "
                        f"{list(changed.keys())}",
                    )
                )
            self._last_snapshot[key_id] = current

        return findings
