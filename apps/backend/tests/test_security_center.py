from __future__ import annotations

import asyncio

from jarvis_backend.event_bus import EventBus
from jarvis_backend.security.security_center import SecurityCenter
from jarvis_backend.security.threat_scoring import ThreatScorer
from jarvis_backend.security.types import FindingSeverity, SecurityCategory, SecurityFinding


def _finding(category=SecurityCategory.PROCESS, severity=FindingSeverity.INFO) -> SecurityFinding:
    return SecurityFinding(category=category, severity=severity, message="test finding")


def test_threat_scorer_escalates_after_consecutive_findings() -> None:
    scorer = ThreatScorer(escalation_threshold=3)

    scorer.score([_finding()])
    scorer.score([_finding()])
    result = scorer.score([_finding()])

    assert result[0].severity == FindingSeverity.WARNING


def test_threat_scorer_resets_when_category_absent() -> None:
    scorer = ThreatScorer(escalation_threshold=2)

    scorer.score([_finding()])
    scorer.score([])  # category absent this cycle — resets the streak
    result = scorer.score([_finding()])

    assert result[0].severity == FindingSeverity.INFO


def test_threat_scorer_never_escalates_past_critical() -> None:
    scorer = ThreatScorer(escalation_threshold=1)

    result = []
    for _ in range(5):
        result = scorer.score([_finding(severity=FindingSeverity.CRITICAL)])

    assert result[0].severity == FindingSeverity.CRITICAL


class _FakeMonitor:
    def __init__(self, name: str, findings: list[SecurityFinding]) -> None:
        self.name = name
        self._findings = findings

    async def scan(self) -> list[SecurityFinding]:
        return self._findings


class _FailingMonitor:
    name = "failing"

    async def scan(self) -> list[SecurityFinding]:
        raise RuntimeError("monitor exploded")


class _FakeSecurityRepository:
    def __init__(self) -> None:
        self.inserted: list[dict] = []

    async def insert_alert(self, *, severity, category, message, requires_approval) -> int:
        self.inserted.append(
            {
                "severity": severity,
                "category": category,
                "message": message,
                "requires_approval": requires_approval,
            }
        )
        return len(self.inserted)


async def test_security_center_runs_all_monitors_and_persists_findings() -> None:
    repository = _FakeSecurityRepository()
    monitor = _FakeMonitor("test", [_finding()])
    center = SecurityCenter([monitor], event_bus=EventBus(), repository=repository)

    findings = await center.run_scan_cycle()

    assert len(findings) == 1
    assert len(repository.inserted) == 1


async def test_security_center_one_monitor_failure_does_not_block_others() -> None:
    repository = _FakeSecurityRepository()
    good_monitor = _FakeMonitor("good", [_finding()])
    center = SecurityCenter(
        [_FailingMonitor(), good_monitor], event_bus=EventBus(), repository=repository
    )

    findings = await center.run_scan_cycle()

    assert len(findings) == 1
    assert len(repository.inserted) == 1


async def test_security_center_publishes_security_alert_events() -> None:
    event_bus = EventBus()
    monitor = _FakeMonitor("test", [_finding(severity=FindingSeverity.WARNING)])
    center = SecurityCenter([monitor], event_bus=event_bus)

    received = []

    async def collect() -> None:
        async for event in event_bus.subscribe():
            received.append(event)
            return

    collector = asyncio.create_task(collect())
    await asyncio.sleep(0)
    await center.run_scan_cycle()
    await asyncio.wait_for(collector, timeout=2)

    assert received[0].type == "security.alert"
    assert received[0].payload.severity == "warning"


async def test_security_center_start_stop_lifecycle() -> None:
    monitor = _FakeMonitor("test", [])
    center = SecurityCenter([monitor], event_bus=EventBus(), scan_interval_s=1000)

    await center.start()
    assert center._task is not None  # noqa: SLF001 - whitebox test
    await center.stop()
    assert center._task is None  # noqa: SLF001 - whitebox test
