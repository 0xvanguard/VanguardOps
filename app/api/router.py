from fastapi import APIRouter
from app.api.endpoints import assets, tickets, workflows

api_router = APIRouter()
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(tickets.router, prefix="/tickets", tags=["tickets"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
