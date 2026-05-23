"""Workflow CRUD operations with atomic state transitions."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select, update
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
        """Atomically transition PENDING/RETRYING -> RUNNING.

        Returns the updated row when the claim succeeded, ``None`` when
        another worker beat us to it (or the workflow was already terminal).
        Implemented as a conditional ``UPDATE ... WHERE status IN (...)``
        which is atomic on every supported backend; eliminates the classic
        TOCTOU race between ``SELECT`` and ``UPDATE``.
        """
        stmt = (
            update(Workflow)
            .where(
                Workflow.id == workflow_id,
                Workflow.status.in_([WorkflowStatus.PENDING, WorkflowStatus.RETRYING]),
            )
            .values(status=WorkflowStatus.RUNNING)
            .execution_options(synchronize_session=False)
        )
        result = db.execute(stmt)
        db.commit()
        if result.rowcount == 0:
            return None
        return db.get(Workflow, workflow_id)


workflow = CRUDWorkflow(Workflow)
