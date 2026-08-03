from fastapi import APIRouter

from . import routes_ai, routes_health, routes_permission, routes_settings, ws_events

api_router = APIRouter()
api_router.include_router(routes_health.router)
api_router.include_router(routes_ai.router)
api_router.include_router(routes_permission.router)
api_router.include_router(routes_settings.router)
api_router.include_router(ws_events.router)

__all__ = ["api_router"]
