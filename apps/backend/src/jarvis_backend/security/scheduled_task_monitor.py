"""Scheduled task monitor — enumerates Windows Task Scheduler entries via
the `schtasks` CLI (subprocess — the same "shell out to a platform tool
rather than a fragile native binding" approach `WhisperCppProvider`/
`PiperProvider` use for their own external tools in `voice/`) and flags
tasks not on a known-entries allowlist.

Same platform posture as `StartupMonitor`/`RegistryMonitor`: Windows-only
concept, honest no-op elsewhere.
"""

from __future__ import annotations

import asyncio
import sys

import structlog

from .types import FindingSeverity, SecurityCategory, SecurityFinding

logger = structlog.get_logger("jarvis_backend.security.scheduled_task_monitor")


class ScheduledTaskMonitor:
    name = "scheduled_task"

    def __init__(self, known_task_names: frozenset[str] = frozenset()) -> None:
        self._known_task_names = known_task_names

    async def scan(self) -> list[SecurityFinding]:
        if sys.platform != "win32":
            logger.debug("scheduled_task_monitor_not_applicable", platform=sys.platform)
            return []

        try:
            process = await asyncio.create_subprocess_exec(
                "schtasks",
                "/query",
                "/fo",
                "CSV",
                "/nh",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
        except FileNotFoundError:
            logger.warning("schtasks_binary_not_found")
            return []

        if process.returncode != 0:
            logger.warning(
                "schtasks_query_failed",
                return_code=process.returncode,
                stderr=stderr.decode("utf-8", errors="replace")[:500],
            )
            return []

        findings: list[SecurityFinding] = []
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            fields = [f.strip('"') for f in line.split('","')]
            if not fields or not fields[0]:
                continue
            task_name = fields[0].lstrip("\\")
            if task_name and task_name not in self._known_task_names:
                findings.append(
                    SecurityFinding(
                        category=SecurityCategory.SCHEDULED_TASK,
                        severity=FindingSeverity.INFO,
                        message=f"Unrecognized scheduled task: {task_name}",
                    )
                )

        return findings
