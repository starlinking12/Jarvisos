from __future__ import annotations

import asyncio
import uuid

from jarvis_contracts import EventSource

from jarvis_backend.agents.permission_broker import PermissionBroker
from jarvis_backend.agents.safety_gate import (
    PermissionDecisionKind,
    PermissionScope,
    SafetyGate,
    SafetyPolicy,
)
from jarvis_backend.event_bus import EventBus


async def test_broker_resolves_pending_request_when_decision_arrives() -> None:
    broker = PermissionBroker(EventBus(), default_timeout_ms=5000)

    async def approve_soon() -> None:
        await asyncio.sleep(0.05)
        pending = list(broker._pending.keys())  # noqa: SLF001 - whitebox test
        assert len(pending) == 1
        broker.resolve(pending[0], True)

    task = asyncio.create_task(approve_soon())
    granted = await broker.request_decision(
        PermissionScope.AUDIO_MICROPHONE.to_request_scope(),
        reason="test",
        requested_by="test",
    )
    await task

    assert granted is True


async def test_broker_times_out_to_denied() -> None:
    broker = PermissionBroker(EventBus(), default_timeout_ms=50)

    granted = await broker.request_decision(
        PermissionScope.AUDIO_MICROPHONE.to_request_scope(),
        reason="test",
        requested_by="test",
    )

    assert granted is False


async def test_broker_resolve_returns_false_for_unknown_request() -> None:
    broker = PermissionBroker(EventBus())
    resolved = broker.resolve(uuid.uuid4(), True)
    assert resolved is False


async def test_safety_gate_prompt_resolves_via_broker() -> None:
    event_bus = EventBus()
    broker = PermissionBroker(event_bus, default_timeout_ms=5000)
    policy = SafetyPolicy(
        overrides={PermissionScope.NETWORK_EGRESS: PermissionDecisionKind.PROMPT}
    )
    gate = SafetyGate(policy, broker=broker)

    async def approve() -> None:
        await asyncio.sleep(0.05)
        pending = list(broker._pending.keys())  # noqa: SLF001 - whitebox test
        broker.resolve(pending[0], True)

    task = asyncio.create_task(approve())
    result = await gate.check(
        PermissionScope.NETWORK_EGRESS,
        reason="test",
        requested_by=EventSource.AGENT_RESEARCH,
        task_id="task-1",
    )
    await task

    assert result.granted is True
    assert result.decision == PermissionDecisionKind.ALLOW


async def test_safety_gate_prompt_without_broker_still_denies() -> None:
    """Confirms ADR-0012's compatibility promise: no broker configured
    means PROMPT resolves to DENY exactly as in Phase 2/3."""
    policy = SafetyPolicy(
        overrides={PermissionScope.NETWORK_EGRESS: PermissionDecisionKind.PROMPT}
    )
    gate = SafetyGate(policy)  # no broker

    result = await gate.check(
        PermissionScope.NETWORK_EGRESS,
        reason="test",
        requested_by=EventSource.AGENT_RESEARCH,
        task_id="task-2",
    )

    assert result.granted is False


async def test_safety_gate_persists_audit_record_when_repository_configured() -> None:
    records = []

    class _FakeAuditRepository:
        async def record(self, *, event, correlation_id, payload):
            records.append((event, correlation_id, payload))

    gate = SafetyGate(SafetyPolicy.production_default(), audit_repository=_FakeAuditRepository())

    await gate.check(
        PermissionScope.FILESYSTEM_WRITE,
        reason="test",
        requested_by=EventSource.AGENT_DEVELOPER,
        task_id="task-3",
    )

    assert len(records) == 1
    assert records[0][0] == "permission_check"
    assert records[0][1] == "task-3"


async def test_safety_gate_audit_persistence_failure_does_not_block_decision() -> None:
    class _FailingAuditRepository:
        async def record(self, *, event, correlation_id, payload):
            raise RuntimeError("db unavailable")

    gate = SafetyGate(
        SafetyPolicy.production_default(), audit_repository=_FailingAuditRepository()
    )

    result = await gate.check(
        PermissionScope.FILESYSTEM_WRITE,
        reason="test",
        requested_by=EventSource.AGENT_DEVELOPER,
        task_id="task-4",
    )
    assert result.granted is False
