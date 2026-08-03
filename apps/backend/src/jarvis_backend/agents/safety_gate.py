"""SafetyGate — the sole authority for whether a tool invocation carrying a
`PermissionScope` is allowed to proceed. No tool, domain agent, or the
Orchestrator itself may bypass this gate — see ADR-0008.

`PermissionScope` is defined here as a Python-side mirror of the
`PermissionScope` enum in `packages/contracts/src/ipc-contracts.ts`. It is
NOT part of `jarvis_contracts` because that package mirrors only
`events.ts` (the main-process ↔ backend event contract); `PermissionScope`
originates on the renderer ↔ main-process IPC contract, which the backend
has no direct part in. The backend needs the same vocabulary because agents
running in this process can request the same categories of high-impact
action — this enum is kept string-value-identical to the TS source.

**Phase 4 update (see ADR-0012):** `PROMPT`-tier scopes now resolve via a
real interactive approval round trip when a `PermissionBroker` is
configured — publishing a `permission.request` event, awaiting the
shell's response (routed through the existing `PermissionGate` dialog),
with a timeout that resolves to `DENY`. Without a configured broker (e.g.
in unit tests, or before `main.py`'s composition root wires one up),
`PROMPT` still resolves to `DENY` exactly as it did in Phase 2/3 — the
fallback behavior never changed, only the non-fallback path gained a real
implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

import structlog
from jarvis_contracts import EventSource, PermissionRequestScope

logger = structlog.get_logger("jarvis_backend.agents.safety_gate")
audit_logger = structlog.get_logger("jarvis_backend.audit")


class PermissionScope(str, Enum):
    FILESYSTEM_WRITE = "filesystem.write"
    PROCESS_CONTROL = "process.control"
    NETWORK_EGRESS = "network.egress"
    AUTOMATION_INPUT = "automation.input"
    SHELL_EXECUTE = "shell.execute"
    AUDIO_MICROPHONE = "audio.microphone"  # Phase 3 — activating live mic capture

    def to_request_scope(self) -> PermissionRequestScope:
        """Converts to the wire-contract enum used by `permission.request`
        events — kept as a distinct type from this one (see module
        docstring's explanation of why `PermissionScope` isn't part of
        `jarvis_contracts`), so this is the one seam where the two are
        bridged."""
        return PermissionRequestScope(self.value)


class PermissionDecisionKind(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    PROMPT = "prompt"  # resolves via PermissionBroker if configured, else DENY


@dataclass(slots=True)
class SafetyPolicy:
    """The declarative policy `SafetyGate` enforces. `default` applies to
    any scope not present in `overrides`. Constructing a policy with
    `default=ALLOW` is intentionally possible (useful for trusted
    development/test environments) but never the production default — see
    `SafetyPolicy.production_default()`."""

    default: PermissionDecisionKind = PermissionDecisionKind.DENY
    overrides: dict[PermissionScope, PermissionDecisionKind] = field(default_factory=dict)

    @staticmethod
    def production_default() -> "SafetyPolicy":
        return SafetyPolicy(default=PermissionDecisionKind.DENY, overrides={})


@dataclass(slots=True, frozen=True)
class PermissionCheckResult:
    granted: bool
    scope: PermissionScope
    decision: PermissionDecisionKind
    reason: str


class PermissionBrokerProtocol(Protocol):
    """Structural interface `SafetyGate` depends on for resolving
    `PROMPT`-tier decisions — satisfied by `PermissionBroker`
    (`agents/permission_broker.py`). Protocol-typed for the same reason
    every other cross-module dependency in this codebase is: `SafetyGate`
    should not need to import a concrete broker implementation to be
    testable or to support a future alternative approval channel."""

    async def request_decision(
        self,
        scope: PermissionRequestScope,
        *,
        reason: str,
        requested_by: str,
        timeout_ms: int | None = None,
    ) -> bool: ...


class AuditRepositoryProtocol(Protocol):
    async def record(
        self, *, event: str, correlation_id: str | None, payload: dict[str, object]
    ) -> None: ...


class SafetyGate:
    def __init__(
        self,
        policy: SafetyPolicy | None = None,
        *,
        broker: PermissionBrokerProtocol | None = None,
        audit_repository: AuditRepositoryProtocol | None = None,
    ) -> None:
        self._policy = policy or SafetyPolicy.production_default()
        self._broker = broker
        self._audit_repository = audit_repository

    async def check(
        self,
        scope: PermissionScope,
        *,
        reason: str,
        requested_by: EventSource,
        task_id: str,
    ) -> PermissionCheckResult:
        configured = self._policy.overrides.get(scope, self._policy.default)

        if configured == PermissionDecisionKind.PROMPT:
            effective = await self._resolve_prompt(scope, reason=reason, requested_by=requested_by)
        else:
            effective = configured

        granted = effective == PermissionDecisionKind.ALLOW

        audit_logger.info(
            "permission_check",
            scope=scope.value,
            requested_by=requested_by.value,
            reason=reason,
            configured_decision=configured.value,
            effective_decision=effective.value,
            granted=granted,
            correlation_id=task_id,
        )
        await self._persist_audit_record(
            scope=scope,
            requested_by=requested_by,
            reason=reason,
            configured=configured,
            effective=effective,
            granted=granted,
            task_id=task_id,
        )

        return PermissionCheckResult(
            granted=granted, scope=scope, decision=effective, reason=reason
        )

    async def _resolve_prompt(
        self, scope: PermissionScope, *, reason: str, requested_by: EventSource
    ) -> PermissionDecisionKind:
        if self._broker is None:
            # See module + class docstrings — no approval channel
            # configured, so this must resolve to DENY, never ALLOW.
            return PermissionDecisionKind.DENY

        granted = await self._broker.request_decision(
            scope.to_request_scope(), reason=reason, requested_by=requested_by.value
        )
        return PermissionDecisionKind.ALLOW if granted else PermissionDecisionKind.DENY

    async def _persist_audit_record(
        self,
        *,
        scope: PermissionScope,
        requested_by: EventSource,
        reason: str,
        configured: PermissionDecisionKind,
        effective: PermissionDecisionKind,
        granted: bool,
        task_id: str,
    ) -> None:
        if self._audit_repository is None:
            return
        try:
            await self._audit_repository.record(
                event="permission_check",
                correlation_id=task_id,
                payload={
                    "scope": scope.value,
                    "requestedBy": requested_by.value,
                    "reason": reason,
                    "configuredDecision": configured.value,
                    "effectiveDecision": effective.value,
                    "granted": granted,
                },
            )
        except Exception:  # noqa: BLE001 - a durable-audit write failure must
            # never block or fail the permission decision itself; the
            # structlog record above is already the guaranteed audit trail.
            logger.warning("audit_persistence_write_failed", exc_info=True)
