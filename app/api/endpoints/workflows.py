"""Workflow endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app import crud
from app.api.deps import (
    DbSession,
    PaginationDep,
    require_operator,
    require_viewer,
)
from app.core.exceptions import WorkflowNotFoundError
from app.models.workflow import WorkflowStatus
from app.schemas.common import Page
from app.schemas.workflow import WorkflowCreate, WorkflowRead

router = APIRouter()


@router.post(
    "/",
    response_model=WorkflowRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator)],
    summary="Manually create a workflow (status forced to PENDING)",
)
def create_workflow(workflow_in: WorkflowCreate, db: DbSession) -> WorkflowRead:
    payload = workflow_in.model_dump()
    payload["status"] = WorkflowStatus.PENDING
    return crud.workflow.create(db=db, obj_in=payload)  # type: ignore[return-value]


@router.get(
    "/",
    response_model=Page[WorkflowRead],
    dependencies=[Depends(require_viewer)],
)
def list_workflows(db: DbSession, pagination: PaginationDep) -> Page[WorkflowRead]:
    items = crud.workflow.get_multi(db=db, skip=pagination.offset, limit=pagination.limit)
    total = crud.workflow.count(db=db)
    return Page[WorkflowRead].build(
        items=[WorkflowRead.model_validate(w) for w in items],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get(
    "/by-ticket/{ticket_id}",
    response_model=list[WorkflowRead],
    dependencies=[Depends(require_viewer)],
)
def list_workflows_by_ticket(
    ticket_id: int,
    db: DbSession,
    pagination: PaginationDep,
) -> list[WorkflowRead]:
    items = crud.workflow.get_by_ticket(
        db=db, ticket_id=ticket_id, skip=pagination.offset, limit=pagination.limit
    )
    return [WorkflowRead.model_validate(w) for w in items]


@router.get(
    "/by-status/{status_value}",
    response_model=list[WorkflowRead],
    dependencies=[Depends(require_viewer)],
)
def list_workflows_by_status(
    status_value: WorkflowStatus,
    db: DbSession,
    pagination: PaginationDep,
) -> list[WorkflowRead]:
    items = crud.workflow.get_by_status(
        db=db, status=status_value, skip=pagination.offset, limit=pagination.limit
    )
    return [WorkflowRead.model_validate(w) for w in items]


@router.get(
    "/{workflow_id}",
    response_model=WorkflowRead,
    dependencies=[Depends(require_viewer)],
)
def get_workflow(workflow_id: int, db: DbSession) -> WorkflowRead:
    db_workflow = crud.workflow.get(db=db, id=workflow_id)
    if db_workflow is None:
        raise WorkflowNotFoundError(f"Workflow {workflow_id} was not found")
    return WorkflowRead.model_validate(db_workflow)
