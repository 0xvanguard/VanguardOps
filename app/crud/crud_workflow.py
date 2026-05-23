"""Workflow CRUD operations with row-level locking for concurrent workers."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.workflow import Workflow, WorkflowStatus
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate


class CRUDWorkflow(CRUDBase[Workflow, WorkflowCreate, WorkflowUpdate]):
    def get_by_ticket(
        self, db: Session, *, ticket_id: int, skip: int = 0, limit: int = 100
    ) -> Sequence[Workflow]:
        stmt = select(Workflow).where(Workflow.ticket_id == ticket_id).offset(skip).limit(limit)
        return db.execute(stmt).scalars().all()

    def get_by_status(
        self,
        db: Session,
        *,
        status: WorkflowStatus,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Workflow]:
        stmt = select(Workflow).where(Workflow.status == status).offset(skip).limit(limit)
        return db.execute(stmt).scalars().all()

    def claim_for_execution(self, db: Session, *, workflow_id: int) -> Workflow | None:
        """Pessimistically claim a workflow for execution.

        Implementation: ``SELECT ... FOR UPDATE SKIP LOCKED`` filtered to rows
        in a claimable status (``PENDING`` or ``RETRYING``). Three branches
        return ``None`` *for the same reason* from the caller's point of view
        (the row should not be executed *now*):

        * the workflow does not exist,
        * the workflow is in a non-claimable status (terminal or already
          ``RUNNING``),
        * the row is locked by another worker (``SKIP LOCKED`` makes our
          query simply not see it).

        Otherwise we transition the row to ``RUNNING`` and ``commit``, which
        releases the row-level lock. The caller can then run the (possibly
        long) workflow body without holding the lock.

        On PostgreSQL this is the recommended pattern for queue-table style
        consumers. On SQLite, ``with_for_update`` is silently ignored: that
        is acceptable in tests because there is exactly one writer.
        """
        stmt = (
            select(Workflow)
            .where(
                Workflow.id == workflow_id,
                Workflow.status.in_([WorkflowStatus.PENDING, WorkflowStatus.RETRYING]),
            )
            .with_for_update(skip_locked=True)
        )
        workflow = db.execute(stmt).scalar_one_or_none()
        if workflow is None:
            # Either missing, locked elsewhere, or in a non-claimable state.
            # Roll back the implicit transaction the SELECT may have started
            # so we don't leak an idle-in-transaction connection.
            db.rollback()
            return None

        workflow.status = WorkflowStatus.RUNNING
        db.commit()  # releases the row-level lock
        return workflow


workflow = CRUDWorkflow(Workflow)
