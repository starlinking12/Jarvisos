"""Settings routes — GET/PUT for persisted user settings. Called directly
by the renderer (content, not a native action — same "renderer talks to
backend HTTP directly" precedent as `routes_ai.py`'s `/ai/chat`, per the
Phase 1 ADR-0001 refinement).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsValue(BaseModel):
    value: Any


class SettingsListResponse(BaseModel):
    settings: dict[str, Any]


@router.get("", response_model=SettingsListResponse)
async def get_all_settings(request: Request) -> SettingsListResponse:
    repository = request.app.state.settings_repository
    all_settings = await repository.list_all()
    return SettingsListResponse(settings=all_settings)


@router.get("/{key}", response_model=SettingsValue)
async def get_setting(request: Request, key: str) -> SettingsValue:
    repository = request.app.state.settings_repository
    value = await repository.get(key)
    return SettingsValue(value=value)


@router.put("/{key}", response_model=SettingsValue)
async def put_setting(request: Request, key: str, body: SettingsValue) -> SettingsValue:
    repository = request.app.state.settings_repository
    await repository.set(key, body.value)
    return body


@router.delete("/{key}")
async def delete_setting(request: Request, key: str) -> dict[str, bool]:
    repository = request.app.state.settings_repository
    await repository.delete(key)
    return {"deleted": True}
