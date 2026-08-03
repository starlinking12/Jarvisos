"""AI chat route.

The renderer calls this directly (not through Electron's IPC bridge) to
submit a user message — per the Phase 1 ADR-0001 refinement, this is
content, not a native/high-impact action, so it doesn't need main-process
gating. The actual response streams back over the WebSocket event bus as
`orchestrator.message` events (see `Orchestrator._synthesize_response`);
this endpoint returns immediately once the Orchestrator's full lifecycle
completes, carrying the final assembled text for callers that don't want
to reassemble it from the stream themselves (e.g. tests, or a future CLI).
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = structlog.get_logger("jarvis_backend.api.routes_ai")

router = APIRouter(prefix="/ai", tags=["ai"])


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID = Field(alias="conversationId")
    message: str

    model_config = {"populate_by_name": True}


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID = Field(alias="conversationId")
    response: str

    model_config = {"populate_by_name": True}


@router.post("/chat", response_model=ChatResponse)
async def post_chat(request: Request, body: ChatRequest) -> ChatResponse:
    orchestrator = request.app.state.orchestrator
    with structlog.contextvars.bound_contextvars(conversation_id=str(body.conversation_id)):
        logger.info("chat_request_received", message_length=len(body.message))
        response_text = await orchestrator.handle_user_message(
            body.conversation_id, body.message
        )
    return ChatResponse(conversationId=body.conversation_id, response=response_text)
