"""Ticket CRUD operations with rich filtering + counting."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.ticket import Ticket, TicketPriority, TicketSeverity, TicketStatus
from app.schemas.ticket import TicketCreate, TicketUpdate


class CRUDTicket(CRUDBase[Ticket, TicketCreate, TicketUpdate]):
    @staticmethod
    def _apply_filters(
        stmt: Select,
        *,
        status: TicketStatus | None,
        severity: TicketSeverity | None,
        priority: TicketPriority | None,
        asset_id: int | None,
    ) -> Select:
        if status is not None:
            stmt = stmt.where(Ticket.status == status)
        if severity is not None:
            stmt = stmt.where(Ticket.severity == severity)
        if priority is not None:
            stmt = stmt.where(Ticket.priority == priority)
        if asset_id is not None:
            stmt = stmt.where(Ticket.asset_id == asset_id)
        return stmt

    def get_multi_with_filters(
        self,
        db: Session,
        *,
        status: TicketStatus | None = None,
        severity: TicketSeverity | None = None,
        priority: TicketPriority | None = None,
        asset_id: int | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Ticket]:
        stmt = (
            self._apply_filters(
                select(Ticket).order_by(Ticket.id.desc()),
                status=status,
                severity=severity,
                priority=priority,
                asset_id=asset_id,
            )
            .offset(skip)
            .limit(limit)
        )
        return db.execute(stmt).scalars().all()

    def count_with_filters(
        self,
        db: Session,
        *,
        status: TicketStatus | None = None,
        severity: TicketSeverity | None = None,
        priority: TicketPriority | None = None,
        asset_id: int | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(Ticket),
            status=status,
            severity=severity,
            priority=priority,
            asset_id=asset_id,
        )
        return int(db.execute(stmt).scalar_one())


ticket = CRUDTicket(Ticket)
