"""SecurityCenter — the composition point for every monitor (ADR-0013).

Runs a periodic scan cycle (`scan_interval_s`, configurable): each
monitor's `scan()` is called independently (one monitor's failure never
blocks the others — a monitor exception is caught, logged, and treated as
"this monitor found nothing this cycle," not a `SecurityCenter` crash),
findings are scored by `ThreatScorer`, then every finding is both
persisted (`SecurityRepository`, durable/queryable) and published live as
a `security.alert` event (`EventBus`) — the schema that has existed
unused since Phase 0 finally has a real publisher.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Protocol

import structlog
from jarvis_contracts import (
    EventSource,
    SecurityAlertCategory,
    SecurityAlertEvent,
    SecurityAlertPayload,
    SecurityAlertSeverity,
)

from jarvis_backend.event_bus import EventBus

from .threat_scoring import ThreatScorer
from .types import SecurityFinding, SecurityMonitor

logger = structlog.get_logger("jarvis_backend.security.security_center")

DEFAULT_SCAN_INTERVAL_S = 300.0  # 5 minutes


class SecurityRepositoryProtocol(Protocol):
    async def insert_alert(
        self, *, severity: str, category: str, message: str, requires_approval: bool
    ) -> int: ...


class SecurityCenter:
    def __init__(
        self,
        monitors: list[SecurityMonitor],
        *,
        event_bus: EventBus,
        repository: SecurityRepositoryProtocol | None = None,
        scorer: ThreatScorer | None = None,
        scan_interval_s: float = DEFAULT_SCAN_INTERVAL_S,
    ) -> None:
        self._monitors = monitors
        self._event_bus = event_bus
        self._repository = repository
        self._scorer = scorer or ThreatScorer()
        self._scan_interval_s = scan_interval_s
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "security_center_started",
            monitor_count=len(self._monitors),
            scan_interval_s=self._scan_interval_s,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("security_center_stopped")

    async def _run_loop(self) -> None:
        while self._running:
            await self.run_scan_cycle()
            await asyncio.sleep(self._scan_interval_s)

    async def run_scan_cycle(self) -> list[SecurityFinding]:
        """Runs every monitor once, scores the combined findings, and
        persists + publishes each one. Public (not `_run_scan_cycle`) so
        tests and a future "scan now" manual trigger can call it directly
        without waiting for the periodic loop."""
        all_findings: list[SecurityFinding] = []

        for monitor in self._monitors:
            try:
                findings = await monitor.scan()
                all_findings.extend(findings)
            except Exception:  # noqa: BLE001 - one monitor's failure must never
                # prevent the others from running or crash the scan cycle.
                logger.warning("monitor_scan_failed", monitor=monitor.name, exc_info=True)

        scored = self._scorer.score(all_findings)

        for finding in scored:
            await self._publish_finding(finding)

        return scored

    async def _publish_finding(self, finding: SecurityFinding) -> None:
        if self._repository is not None:
            try:
                await self._repository.insert_alert(
                    severity=finding.severity.value,
                    category=finding.category.value,
                    message=finding.message,
                    requires_approval=finding.requires_approval,
                )
            except Exception:  # noqa: BLE001 - a persistence failure must not
                # block the live event publish below; the finding is still
                # observable in real time even if durable storage failed.
                logger.warning("security_alert_persistence_failed", exc_info=True)

        await self._event_bus.publish(
            SecurityAlertEvent(
                id=uuid.uuid4(),
                source=EventSource.AGENT_SECURITY,
                timestamp=datetime.now(UTC),
                payload=SecurityAlertPayload(
                    severity=SecurityAlertSeverity(finding.severity.value),
                    category=SecurityAlertCategory(finding.category.value),
                    message=finding.message,
                    requires_approval=finding.requires_approval,
                ),
            )
        )
