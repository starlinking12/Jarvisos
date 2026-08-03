"""Permission decision route — the other half of the backend→shell
permission RPC (see ADR-0012, `agents/permission_broker.py`). The shell's
`PermissionBridge` (`apps/shell/src/main/backend/PermissionBridge.ts`)
POSTs here once the user has answered the `PermissionGate` dialog shown
in response to a `permission.request` event.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = structlog.get_logger("jarvis_backend.api.routes_permission")

router = APIRouter(prefix="/agent", tags=["permission"])


class PermissionDecisionRequest(BaseModel):
    request_id: uuid.UUID = Field(alias="requestId")
    granted: bool

    model_config = {"populate_by_name": True}


class PermissionDecisionResponse(BaseModel):
    request_id: uuid.UUID = Field(alias="requestId")
    resolved: bool

    model_config = {"populate_by_name": True}


@router.post("/permission-decision", response_model=PermissionDecisionResponse)
async def post_permission_decision(
    request: Request, body: PermissionDecisionRequest
) -> PermissionDecisionResponse:
    broker = request.app.state.permission_broker
    if broker is None:
        raise HTTPException(status_code=503, detail="Permission broker is not configured")

    resolved = broker.resolve(body.request_id, body.granted)
    if not resolved:
        logger.warning(
            "permission_decision_for_unknown_request",
            request_id=str(body.request_id),
        )
        raise HTTPException(
            status_code=404,
            detail=f"No pending permission request with id '{body.request_id}' "
            "(it may have already timed out).",
        )

    return PermissionDecisionResponse(requestId=body.request_id, resolved=True)
