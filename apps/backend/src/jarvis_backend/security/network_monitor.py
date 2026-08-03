"""Network monitor — cross-platform via `psutil`. Flags listening ports
not on an allowlist (a fresh, unexpected listener is a common early
indicator of compromise), without pretending to be a full IDS.
"""

from __future__ import annotations

from typing import Any

import structlog

from .process_monitor import PsutilUnavailableError
from .types import FindingSeverity, SecurityCategory, SecurityFinding

logger = structlog.get_logger("jarvis_backend.security.network_monitor")

DEFAULT_ALLOWED_LISTEN_PORTS = frozenset({8137})  # the backend's own port


class NetworkMonitor:
    name = "network"

    def __init__(
        self, allowed_listen_ports: frozenset[int] = DEFAULT_ALLOWED_LISTEN_PORTS
    ) -> None:
        self._psutil: Any = self._import_psutil()
        self._allowed_listen_ports = allowed_listen_ports

    @staticmethod
    def _import_psutil() -> Any:
        try:
            import psutil  # type: ignore[import-untyped]
        except ImportError as error:
            raise PsutilUnavailableError() from error
        return psutil

    async def scan(self) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []

        try:
            connections = self._psutil.net_connections(kind="inet")
        except (PermissionError, self._psutil.AccessDenied):
            logger.warning("network_scan_requires_elevated_privileges")
            return findings

        for conn in connections:
            if conn.status == "LISTEN" and conn.laddr:
                port = conn.laddr.port
                if port not in self._allowed_listen_ports and port >= 1024:
                    # Privileged ports (<1024) are typically OS/system
                    # services with their own established trust model;
                    # unexpected high-numbered listeners are the more
                    # actionable signal for a desktop assistant to flag.
                    findings.append(
                        SecurityFinding(
                            category=SecurityCategory.NETWORK,
                            severity=FindingSeverity.WARNING,
                            message=f"Unexpected process listening on port {port} "
                            f"(pid {conn.pid})",
                        )
                    )

        return findings
