from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from jarvis_contracts import BackendHealthEvent, BackendHealthPayload, EventSource

from jarvis_backend.event_bus import EventBus


def _make_health_event() -> BackendHealthEvent:
    return BackendHealthEvent(
        id=uuid.uuid4(),
        source=EventSource.BACKEND,
        timestamp=datetime.now(UTC),
        payload=BackendHealthPayload(status="ok", uptime_ms=1000, loaded_models=[]),
    )


async def test_subscriber_receives_published_event() -> None:
    bus = EventBus()

    async def subscriber() -> BackendHealthEvent:
        async for event in bus.subscribe():
            return event
        raise AssertionError("subscriber generator exited without yielding")

    task = asyncio.create_task(subscriber())
    await asyncio.sleep(0)
    await bus.publish(_make_health_event())

    received = await asyncio.wait_for(task, timeout=2)
    assert received.type == "backend.health"


async def test_multiple_subscribers_each_receive_the_event() -> None:
    bus = EventBus()
    results: list[str] = []

    async def subscriber(name: str) -> None:
        async for _event in bus.subscribe():
            results.append(name)
            return

    task_a = asyncio.create_task(subscriber("a"))
    task_b = asyncio.create_task(subscriber("b"))
    await asyncio.sleep(0)

    await bus.publish(_make_health_event())
    await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=2)

    assert sorted(results) == ["a", "b"]


async def test_subscriber_count_reflects_active_subscribers() -> None:
    bus = EventBus()
    assert bus.subscriber_count() == 0

    async def subscriber() -> None:
        async for _event in bus.subscribe():
            return

    task = asyncio.create_task(subscriber())
    await asyncio.sleep(0)
    assert bus.subscriber_count() == 1

    await bus.publish(_make_health_event())
    await asyncio.wait_for(task, timeout=2)
    await asyncio.sleep(0)
    assert bus.subscriber_count() == 0


async def test_publish_to_full_queue_drops_oldest_without_raising() -> None:
    """Whitebox test: registers a raw queue directly (bypassing the active
    `subscribe()` consumer loop, which would otherwise hand off each
    published event directly to a waiting `get()` rather than actually
    filling the buffer) so the queue genuinely fills to `max_queue_size`
    and the drop-oldest branch in `publish()` is exercised deterministically,
    without relying on task-scheduling timing.
    """
    bus = EventBus(max_queue_size=1)
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    bus._subscribers.add(queue)  # noqa: SLF001 - intentional whitebox access, see docstring

    first_event = _make_health_event()
    second_event = _make_health_event()

    await bus.publish(first_event)  # queue: [first_event]
    assert queue.full()

    await bus.publish(second_event)  # should drop first_event, not raise

    assert queue.qsize() == 1
    remaining = queue.get_nowait()
    assert remaining.id == second_event.id
