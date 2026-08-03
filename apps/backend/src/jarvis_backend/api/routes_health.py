"""Health/status endpoint.

This is what BackendSupervisor's readiness detection graduates to once the
HTTP server is up (Phase 1 adds an HTTP readiness poll alongside the current
stdout-log heuristic in BackendSupervisor.ts).
"""

from __future__ import annotations

import time

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["health"])

_PROCESS_STARTED_AT = time.monotonic()


class HealthResponse(BaseModel):
    status: str
    uptime_ms: int
    loaded_models: list[str] = []


@router.get("", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    uptime_ms = int((time.monotonic() - _PROCESS_STARTED_AT) * 1000)
    # loaded_models stays empty until the ModelRouter (Phase 2) reports in.
    return HealthResponse(status="ok", uptime_ms=uptime_ms, loaded_models=[])
