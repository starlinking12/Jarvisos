"""Async, in-process publish/subscribe event bus.

This is the backbone of the backend's event-driven architecture: the
Orchestrator and every agent publish `JarvisEvent`s here rather than calling
each other directly, and the WebSocket layer (`api/ws_events.py`) subscribes
to forward events out to the Electron shell. This keeps agents decoupled
from both each other and from the transport layer, per the "every subsystem
must be replaceable" principle.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from jarvis_contracts import JarvisEvent

logger = logging.getLogger("jarvis_backend.event_bus")


class EventBus:
    """A minimal fan-out pub/sub bus built on asyncio queues.

    Each subscriber gets its own bounded queue so a slow consumer (e.g. a
    lagging WebSocket client) cannot block publishers or other subscribers.
    When a subscriber's queue is full, the oldest event is dropped and a
    warning is logged — favoring liveness over completeness for HUD-facing
    event streams. Callers needing guaranteed delivery (e.g. security
    alerts) should persist state themselves rather than relying solely on
    the bus.
    """

    def __init__(self, max_queue_size: int = 256) -> None:
        self._subscribers: set[asyncio.Queue[JarvisEvent]] = set()
        self._max_queue_size = max_queue_size
        self._lock = asyncio.Lock()

    async def publish(self, event: JarvisEvent) -> None:
        async with self._lock:
            subscribers = list(self._subscribers)

        for queue in subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                    logger.warning(
                        "Subscriber queue full — dropped oldest event",
                        extra={"event_type": event.type},
                    )
                except asyncio.QueueEmpty:
                    pass
            await queue.put(event)

    async def subscribe(self) -> AsyncIterator[JarvisEvent]:
        queue: asyncio.Queue[JarvisEvent] = asyncio.Queue(
            maxsize=self._max_queue_size
        )
        async with self._lock:
            self._subscribers.add(queue)

        try:
            while True:
                yield await queue.get()
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Process-wide singleton. The backend runs as a single Electron-supervised
# child process (ADR-0001), so a module-level singleton is appropriate here;
# it is still injected via FastAPI dependency (see api/ws_events.py) rather
# than imported directly by route handlers, keeping the door open for
# per-request/test overrides.
event_bus = EventBus()
