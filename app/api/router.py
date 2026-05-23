"""Top-level API router that mounts every endpoint module under ``/api/v1``."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.endpoints import (
    activity_log,
    assets,
    auth,
    tickets,
    workflows,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(tickets.router, prefix="/tickets", tags=["tickets"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(activity_log.router, prefix="/activity-log", tags=["activity-log"])
