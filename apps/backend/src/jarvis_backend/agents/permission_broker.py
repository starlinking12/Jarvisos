"""PermissionBroker — the piece ADR-0004 flagged as missing: a real
channel for a backend-originated `PROMPT`-tier permission request to
reach the Electron-side `PermissionGate` dialog and get an answer back.
See ADR-0012 for the full design.

Flow:
  1. `SafetyGate` (for a `PROMPT`-tier scope) calls
     `PermissionBroker.request_decision(...)`.
  2. The broker registers a pending `asyncio.Future` keyed by a fresh
     `request_id`, publishes a `permission.request` event over the
     `EventBus` (received by the shell's WS client — see
     `apps/shell/src/main/backend/PermissionBridge.ts`), and awaits the
     future with a timeout.
  3. The shell shows its existing `PermissionGate` dialog and POSTs the
     decision to the backend's `POST /agent/permission-decision` endpoint
     (`api/routes_permission.py`), which resolves the matching future.
  4. If no response arrives within `timeout_ms`, the future is resolved
     to `False` (denied) — an unanswered prompt must never silently grant
     access, matching every other "absence of a definite ALLOW means
     DENY" rule this project enforces (ADR-0004).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import structlog
from jarvis_contracts import (
    EventSource,
    PermissionRequestEvent,
    PermissionRequestEventPayload,
    PermissionRequestScope,
)

from jarvis_backend.event_bus import EventBus

logger = structlog.get_logger("jarvis_backend.agents.permission_broker")

DEFAULT_TIMEOUT_MS = 30_000


class PermissionBroker:
    def __init__(
        self, event_bus: EventBus, *, default_timeout_ms: int = DEFAULT_TIMEOUT_MS
    ) -> None:
        self._event_bus = event_bus
        self._default_timeout_ms = default_timeout_ms
        self._pending: dict[uuid.UUID, asyncio.Future[bool]] = {}

    async def request_decision(
        self,
        scope: PermissionRequestScope,
        *,
        reason: str,
        requested_by: str,
        timeout_ms: int | None = None,
    ) -> bool:
        request_id = uuid.uuid4()
        effective_timeout_ms = timeout_ms or self._default_timeout_ms
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        await self._event_bus.publish(
            PermissionRequestEvent(
                id=uuid.uuid4(),
                source=EventSource.BACKEND,
                timestamp=datetime.now(UTC),
                payload=PermissionRequestEventPayload(
                    request_id=request_id,
                    scope=scope,
                    reason=reason,
                    requested_by=requested_by,
                    timeout_ms=effective_timeout_ms,
                ),
            )
        )
        logger.info(
            "permission_request_sent",
            request_id=str(request_id),
            scope=scope.value,
            timeout_ms=effective_timeout_ms,
        )

        try:
            granted = await asyncio.wait_for(future, timeout=effective_timeout_ms / 1000)
        except TimeoutError:
            logger.warning("permission_request_timed_out", request_id=str(request_id))
            granted = False
        finally:
            self._pending.pop(request_id, None)

        return granted

    def resolve(self, request_id: uuid.UUID, granted: bool) -> bool:
        """Called by the HTTP decision endpoint when the shell responds.
        Returns True if a pending request was actually found and
        resolved, False if `request_id` is unknown (already timed out, or
        never existed — the caller should treat this as a 404, not an
        error worth crashing over)."""
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(granted)
        logger.info("permission_request_resolved", request_id=str(request_id), granted=granted)
        return True

    def pending_count(self) -> int:
        return len(self._pending)
