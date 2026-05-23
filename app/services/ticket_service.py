"""Ticket orchestration: creation, state-machine updates, audit emission.

The endpoint layer is intentionally thin: it parses input, calls a single
service method, then returns the model. All business decisions (priority
calculation, SLA, assignment, audit logging, workflow dispatch, state
transition checks) live here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app import crud
from app.core.exceptions import (
    AssetNotFoundError,
    InvalidStateTransitionError,
    TicketNotFoundError,
)
from app.models.ticket import (
    TICKET_STATE_MACHINE,
    Ticket,
    TicketStatus,
)
from app.schemas.ticket import TicketCreate, TicketUpdate
from app.services.activity_log_service import activity_log_service
from app.services.assignment_service import assignment_service
from app.services.rules import SLA_HOURS, calculate_priority


class TicketService:
    """Orchestrates the lifecycle of a ticket."""

    # -- Creation -------------------------------------------------------

    @staticmethod
    def process_new_ticket(
        db: Session,
        ticket_in: TicketCreate,
        *,
        actor_id: str | None = None,
    ) -> Ticket:
        """Create a ticket, applying triage rules and emitting full audit trail.

        Steps:
        1. Validate referential integrity (``asset_id`` must exist).
        2. Compute final priority from severity + category.
        3. Compute SLA ``due_at`` from priority.
        4. Resolve initial assignee from category.
        5. Persist.
        6. Emit ``ticket_created``, ``ticket_prioritized`` and
           ``ticket_assigned`` events into the audit log.
        7. Trigger downstream workflow (if any) via the workflow service.
        """
        # 1. Validate asset
        if ticket_in.asset_id is not None:
            if crud.asset.get(db=db, id=ticket_in.asset_id) is None:
                raise AssetNotFoundError(
                    f"Asset {ticket_in.asset_id} does not exist",
                    extras={"asset_id": ticket_in.asset_id},
                )

        # 2. Priority
        priority = calculate_priority(ticket_in.severity, ticket_in.category)

        # 3. SLA
        sla_hours = SLA_HOURS.get(priority, 24)
        due_at = datetime.now(UTC) + timedelta(hours=sla_hours)

        # 4. Assignment
        assignee = assignment_service.get_initial_assignment(ticket_in.category)

        # 5. Persist
        payload = ticket_in.model_dump()
        payload.update(
            priority=priority,
            assigned_to=assignee,
            due_at=due_at,
            status=TicketStatus.OPEN,
        )
        db_ticket = crud.ticket.create(db=db, obj_in=payload)

        # 6. Audit trail (one event per concern, makes timelines readable)
        common = {"actor_id": actor_id, "actor_type": "user" if actor_id else "system"}
        activity_log_service.log_event(
            db=db,
            event_type="ticket_created",
            entity_type="ticket",
            entity_id=db_ticket.id,
            details={
                "title": db_ticket.title,
                "category": db_ticket.category,
                "severity": db_ticket.severity.value,
            },
            **common,
        )
        activity_log_service.log_event(
            db=db,
            event_type="ticket_prioritized",
            entity_type="ticket",
            entity_id=db_ticket.id,
            details={
                "priority": priority.value,
                "sla_hours": sla_hours,
                "due_at": due_at.isoformat(),
            },
            **common,
        )
        activity_log_service.log_event(
            db=db,
            event_type="ticket_assigned",
            entity_type="ticket",
            entity_id=db_ticket.id,
            details={"assigned_to": assignee},
            **common,
        )

        # 7. Trigger downstream workflow (lazy import avoids circular deps)
        from app.services.workflow_service import workflow_service

        workflow_service.trigger_workflow_for_ticket(
            db=db,
            ticket_id=db_ticket.id,
            category=ticket_in.category,
            actor_id=actor_id,
        )

        return db_ticket

    # -- Update with state machine --------------------------------------

    @staticmethod
    def update_ticket(
        db: Session,
        *,
        ticket_id: int,
        update_in: TicketUpdate,
        actor_id: str | None = None,
    ) -> Ticket:
        db_ticket = crud.ticket.get(db=db, id=ticket_id)
        if db_ticket is None:
            raise TicketNotFoundError(
                f"Ticket {ticket_id} was not found",
                extras={"ticket_id": ticket_id},
            )

        update_data = update_in.model_dump(exclude_unset=True)

        # Validate state transition before applying anything
        if "status" in update_data and update_data["status"] != db_ticket.status:
            new_status: TicketStatus = update_data["status"]
            allowed = TICKET_STATE_MACHINE.get(db_ticket.status, set())
            if new_status not in allowed:
                raise InvalidStateTransitionError(
                    f"Cannot transition ticket from {db_ticket.status.value} to {new_status.value}",
                    extras={
                        "current_status": db_ticket.status.value,
                        "requested_status": new_status.value,
                        "allowed_transitions": sorted(s.value for s in allowed),
                    },
                )

        # Validate referential integrity if asset_id is being changed
        if "asset_id" in update_data and update_data["asset_id"] is not None:
            if crud.asset.get(db=db, id=update_data["asset_id"]) is None:
                raise AssetNotFoundError(
                    f"Asset {update_data['asset_id']} does not exist",
                    extras={"asset_id": update_data["asset_id"]},
                )

        # Capture transition details for audit before mutating
        transition: dict[str, Any] | None = None
        if "status" in update_data and update_data["status"] != db_ticket.status:
            transition = {
                "from": db_ticket.status.value,
                "to": update_data["status"].value,
            }

        updated = crud.ticket.update(db=db, db_obj=db_ticket, obj_in=update_data)

        common = {"actor_id": actor_id, "actor_type": "user" if actor_id else "system"}
        activity_log_service.log_event(
            db=db,
            event_type="ticket_updated",
            entity_type="ticket",
            entity_id=updated.id,
            details={"updated_fields": update_data},
            **common,
        )
        if transition is not None:
            activity_log_service.log_event(
                db=db,
                event_type="ticket_status_changed",
                entity_type="ticket",
                entity_id=updated.id,
                details=transition,
                **common,
            )
        return updated


ticket_service = TicketService()
