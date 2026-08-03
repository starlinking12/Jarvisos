"""WebSocket endpoint that forwards EventBus events to the Electron shell.

This is the Python side of the `packages/contracts/src/events.ts` contract:
every message sent over this socket is a `JarvisEvent`, serialized with
pydantic's `model_dump_json(by_alias=True)` so field names match the
camelCase TypeScript schema exactly.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from jarvis_backend.event_bus import event_bus

logger = logging.getLogger("jarvis_backend.api.ws_events")

router = APIRouter()


@router.websocket("/ws/events")
async def events_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("Shell connected to event stream")

    try:
        async for event in event_bus.subscribe():
            await websocket.send_text(event.model_dump_json(by_alias=True))
    except WebSocketDisconnect:
        logger.info("Shell disconnected from event stream")
    except Exception:  # noqa: BLE001 - log and let the connection close cleanly
        logger.exception("Event stream terminated unexpectedly")
