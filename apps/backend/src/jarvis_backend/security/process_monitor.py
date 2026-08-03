"""Process monitor — cross-platform via `psutil` (optional `[security]`
dependency, lazy-imported per this project's established pattern for
native/optional libraries — see `voice/config.py`'s module docstring for
the precedent).

Baseline heuristics for Phase 4 (real, working rules — not exhaustive
threat intelligence, which is explicitly out of scope for a local
assistant's built-in monitor and would need a maintained signature feed
this project doesn't have): flags processes running from suspicious
locations (temp directories), and a configurable denylist of
known-suspicious process names.
"""

from __future__ import annotations

from typing import Any

import structlog

from .types import FindingSeverity, SecurityCategory, SecurityFinding

logger = structlog.get_logger("jarvis_backend.security.process_monitor")

SUSPICIOUS_PATH_FRAGMENTS = ("\\temp\\", "/tmp/", "\\appdata\\local\\temp\\")


class PsutilUnavailableError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "'psutil' is required for process/network monitoring but is not "
            "installed. Install it with: pip install 'jarvis-backend[security]'"
        )


class ProcessMonitor:
    name = "process"

    def __init__(self, denylist_names: frozenset[str] = frozenset()) -> None:
        self._psutil: Any = self._import_psutil()
        self._denylist_names = {n.lower() for n in denylist_names}

    @staticmethod
    def _import_psutil() -> Any:
        try:
            import psutil  # type: ignore[import-untyped]
        except ImportError as error:
            raise PsutilUnavailableError() from error
        return psutil

    async def scan(self) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []

        for proc in self._psutil.process_iter(["pid", "name", "exe"]):
            try:
                info = proc.info
                name = (info.get("name") or "").lower()
                exe = info.get("exe") or ""

                if name in self._denylist_names:
                    findings.append(
                        SecurityFinding(
                            category=SecurityCategory.PROCESS,
                            severity=FindingSeverity.CRITICAL,
                            message=f"Denylisted process running: {info.get('name')} "
                            f"(pid {info.get('pid')})",
                            requires_approval=True,
                        )
                    )
                    continue

                if exe and any(frag in exe.lower() for frag in SUSPICIOUS_PATH_FRAGMENTS):
                    findings.append(
                        SecurityFinding(
                            category=SecurityCategory.PROCESS,
                            severity=FindingSeverity.WARNING,
                            message=f"Process running from a temporary directory: "
                            f"{info.get('name')} ({exe})",
                        )
                    )
            except (self._psutil.NoSuchProcess, self._psutil.AccessDenied):
                # Processes can exit between iteration and info access, or
                # be inaccessible without elevated privileges — neither is
                # itself a finding worth reporting.
                continue

        return findings
