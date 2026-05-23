"""Ticket endpoints (CRUD with state-machine validation)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app import crud
from app.api.deps import (
    CurrentUser,
    DbSession,
    PaginationDep,
    require_operator,
    require_viewer,
)
from app.core.exceptions import TicketNotFoundError
from app.models.ticket import TicketPriority, TicketSeverity, TicketStatus
from app.schemas.common import Page
from app.schemas.ticket import TicketCreate, TicketRead, TicketUpdate
from app.services.ticket_service import ticket_service

router = APIRouter()


@router.post(
    "/",
    response_model=TicketRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator)],
    summary="Create a ticket (auto-priority, auto-assign, audit + workflow)",
)
def create_ticket(
    ticket_in: TicketCreate,
    db: DbSession,
    current: CurrentUser,
) -> TicketRead:
    db_ticket = ticket_service.process_new_ticket(
        db=db, ticket_in=ticket_in, actor_id=str(current.id)
    )
    return TicketRead.model_validate(db_ticket)


@router.get(
    "/",
    response_model=Page[TicketRead],
    dependencies=[Depends(require_viewer)],
    summary="List tickets (paginated)",
)
def list_tickets(db: DbSession, pagination: PaginationDep) -> Page[TicketRead]:
    items = crud.ticket.get_multi_with_filters(
        db=db, skip=pagination.offset, limit=pagination.limit
    )
    total = crud.ticket.count_with_filters(db=db)
    return Page[TicketRead].build(
        items=[TicketRead.model_validate(t) for t in items],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get(
    "/filter",
    response_model=Page[TicketRead],
    dependencies=[Depends(require_viewer)],
    summary="Filter tickets by status / severity / priority / asset_id",
)
def filter_tickets(
    db: DbSession,
    pagination: PaginationDep,
    status_value: TicketStatus | None = None,
    severity: TicketSeverity | None = None,
    priority: TicketPriority | None = None,
    asset_id: int | None = None,
) -> Page[TicketRead]:
    items = crud.ticket.get_multi_with_filters(
        db=db,
        status=status_value,
        severity=severity,
        priority=priority,
        asset_id=asset_id,
        skip=pagination.offset,
        limit=pagination.limit,
    )
    total = crud.ticket.count_with_filters(
        db=db,
        status=status_value,
        severity=severity,
        priority=priority,
        asset_id=asset_id,
    )
    return Page[TicketRead].build(
        items=[TicketRead.model_validate(t) for t in items],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get(
    "/{ticket_id}",
    response_model=TicketRead,
    dependencies=[Depends(require_viewer)],
)
def get_ticket(ticket_id: int, db: DbSession) -> TicketRead:
    db_ticket = crud.ticket.get(db=db, id=ticket_id)
    if db_ticket is None:
        raise TicketNotFoundError(f"Ticket {ticket_id} was not found")
    return TicketRead.model_validate(db_ticket)


@router.patch(
    "/{ticket_id}",
    response_model=TicketRead,
    dependencies=[Depends(require_operator)],
    summary="Update a ticket (state-machine validated)",
)
def update_ticket(
    ticket_id: int,
    ticket_in: TicketUpdate,
    db: DbSession,
    current: CurrentUser,
) -> TicketRead:
    updated = ticket_service.update_ticket(
        db=db,
        ticket_id=ticket_id,
        update_in=ticket_in,
        actor_id=str(current.id),
    )
    return TicketRead.model_validate(updated)
