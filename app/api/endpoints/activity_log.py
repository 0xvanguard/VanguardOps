"""Activity-log read endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import crud
from app.api.deps import (
    DbSession,
    PaginationDep,
    require_viewer,
)
from app.schemas.activity_log import ActivityLogRead
from app.schemas.common import Page

router = APIRouter()


@router.get(
    "/",
    response_model=Page[ActivityLogRead],
    dependencies=[Depends(require_viewer)],
    summary="List all audit events (paginated, newest first)",
)
def list_logs(db: DbSession, pagination: PaginationDep) -> Page[ActivityLogRead]:
    items = crud.activity_log.get_multi_ordered(
        db=db, skip=pagination.offset, limit=pagination.limit
    )
    total = crud.activity_log.count(db=db)
    return Page[ActivityLogRead].build(
        items=[ActivityLogRead.model_validate(a) for a in items],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get(
    "/{entity_type}/{entity_id}",
    response_model=list[ActivityLogRead],
    dependencies=[Depends(require_viewer)],
    summary="List audit events for a single entity (newest first)",
)
def list_logs_by_entity(
    entity_type: str,
    entity_id: int,
    db: DbSession,
    pagination: PaginationDep,
) -> list[ActivityLogRead]:
    items = crud.activity_log.get_by_entity(
        db=db,
        entity_type=entity_type,
        entity_id=entity_id,
        skip=pagination.offset,
        limit=pagination.limit,
    )
    return [ActivityLogRead.model_validate(a) for a in items]
