"""Workflow orchestration: persistence, audit, async dispatch.

The dispatch step intentionally tolerates a missing broker (Celery would
raise when called outside an integration environment). When the configured
``CELERY_TASK_ALWAYS_EAGER`` flag is set we run the task inline so unit
tests don't need a Redis container.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app import crud
from app.core.config import get_settings
from app.models.workflow import WorkflowStatus
from app.schemas.workflow import WorkflowCreate
from app.services.activity_log_service import activity_log_service
from app.services.rules import workflow_for_category

logger = logging.getLogger(__name__)


class WorkflowService:
    @staticmethod
    def trigger_workflow_for_ticket(
        db: Session,
        *,
        ticket_id: int,
        category: str | None,
        actor_id: str | None = None,
    ):
        """Create a Workflow row and (optionally) enqueue its async run.

        Returns the persisted :class:`Workflow` row, or ``None`` if the
        category does not map to any workflow.
        """
        workflow_name = workflow_for_category(category)
        if not workflow_name:
            return None

        workflow_in = WorkflowCreate(
            name=workflow_name,
            trigger_type="ticket_created",
            description=f"Auto-triggered for ticket {ticket_id}",
            ticket_id=ticket_id,
            config_data={"target_category": category},
        )
        # Persist with PENDING status (defaulted by the column).
        payload = workflow_in.model_dump()
        payload["status"] = WorkflowStatus.PENDING
        db_workflow = crud.workflow.create(db=db, obj_in=payload)

        common = {"actor_id": actor_id, "actor_type": "user" if actor_id else "system"}
        activity_log_service.log_event(
            db=db,
            event_type="workflow_triggered",
            entity_type="ticket",
            entity_id=ticket_id,
            details={
                "workflow_id": db_workflow.id,
                "workflow_name": workflow_name,
            },
            **common,
        )

        WorkflowService._dispatch(db=db, workflow_id=db_workflow.id, actor_id=actor_id)
        return db_workflow

    @staticmethod
    def _dispatch(db: Session, *, workflow_id: int, actor_id: str | None) -> None:
        """Best-effort enqueue of the Celery task.

        Failures (e.g. broker unreachable in dev) must NOT roll back the
        creation of the workflow row - the row is the source of truth and
        an admin can re-enqueue later.
        """
        from app.workers.tasks import execute_workflow_task

        settings = get_settings()
        try:
            if settings.CELERY_TASK_ALWAYS_EAGER:
                # Eager mode: run synchronously (test convenience).
                result = execute_workflow_task.apply(args=[workflow_id])
                task_id = result.id if result is not None else "eager"
            else:
                async_result = execute_workflow_task.delay(workflow_id)
                task_id = async_result.id
            activity_log_service.log_event(
                db=db,
                event_type="workflow_enqueued",
                entity_type="workflow",
                entity_id=workflow_id,
                details={"celery_task_id": task_id},
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
            )
        except Exception as exc:  # broker unreachable, etc.
            logger.warning(
                "workflow_enqueue_failed", extra={"workflow_id": workflow_id, "error": str(exc)}
            )
            activity_log_service.log_event(
                db=db,
                event_type="workflow_enqueue_failed",
                entity_type="workflow",
                entity_id=workflow_id,
                details={"error": str(exc)},
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
            )


workflow_service = WorkflowService()
