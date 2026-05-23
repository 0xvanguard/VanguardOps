"""Celery tasks.

Design highlights
-----------------
* The task function is split in two: a pure :func:`run_workflow_execution`
  that takes a session and is therefore unit-testable, and a thin
  :func:`execute_workflow_task` Celery wrapper. Tests can import either.
* The PENDING -> RUNNING transition uses a conditional ``UPDATE`` performed
  by ``crud.workflow.claim_for_execution`` so two workers can never run
  the same workflow concurrently.
* All session lifecycle is handled inside the task; we never share a
  session with the API process.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app import crud
from app.database import SessionLocal
from app.models.workflow import TERMINAL_WORKFLOW_STATUSES, WorkflowStatus
from app.services.activity_log_service import activity_log_service
from app.workers.celery_app import celery_app
from app.workers.workflow_executor import WorkflowExecutor


def _make_session() -> Session:
    """Hook for tests to inject a session factory."""
    return SessionLocal()


def run_workflow_execution(
    workflow_id: int,
    *,
    session_factory=None,
    task_id: str | None = None,
    retries: int = 0,
    max_retries: int = 0,
) -> dict[str, Any]:
    """Execute a single workflow run inside a fresh DB session.

    This function is the *pure* core of the Celery task: it has no Celery
    state and can therefore be invoked from tests directly.

    Returns a dict with either a ``status``/``result`` payload (success)
    or an ``error`` key (failure). Re-raises only when the caller (the
    Celery wrapper) needs Celery to perform a retry.
    """
    session_factory = session_factory or _make_session
    db = session_factory()
    try:
        workflow = crud.workflow.get(db=db, id=workflow_id)
        if workflow is None:
            return {"error": "workflow_not_found", "workflow_id": workflow_id}

        # Atomic claim: PENDING/RETRYING -> RUNNING in a single UPDATE.
        claimed = crud.workflow.claim_for_execution(db=db, workflow_id=workflow_id)
        if claimed is None:
            # Either someone else is running it, or it's already terminal.
            activity_log_service.log_event(
                db=db,
                event_type="workflow_skipped_duplicate",
                entity_type="workflow",
                entity_id=workflow_id,
                details={
                    "current_status": workflow.status.value,
                    "msg": "Execution skipped: workflow not in PENDING/RETRYING.",
                },
            )
            return {"error": "Skipped due to status", "current_status": workflow.status.value}

        activity_log_service.log_event(
            db=db,
            event_type="workflow_started",
            entity_type="workflow",
            entity_id=workflow_id,
            details={"worker_task_id": task_id},
        )

        try:
            result = WorkflowExecutor.run_workflow(claimed.name, claimed.config_data or {})
        except Exception as exec_error:
            return _handle_failure(
                db=db,
                workflow_id=workflow_id,
                error=exec_error,
                retries=retries,
                max_retries=max_retries,
            )

        # Success path
        claimed.status = WorkflowStatus.SUCCESS
        claimed.execution_logs = result
        db.commit()
        activity_log_service.log_event(
            db=db,
            event_type="workflow_succeeded",
            entity_type="workflow",
            entity_id=workflow_id,
            details={"result": result},
        )
        return result
    finally:
        db.close()


def _handle_failure(
    *,
    db: Session,
    workflow_id: int,
    error: Exception,
    retries: int,
    max_retries: int,
) -> dict[str, Any]:
    """Mark workflow as RETRYING or FAILED depending on retry budget."""
    db.rollback()
    workflow = crud.workflow.get(db=db, id=workflow_id)
    if workflow is None:
        return {"error": str(error)}

    if retries < max_retries and workflow.status not in TERMINAL_WORKFLOW_STATUSES:
        workflow.status = WorkflowStatus.RETRYING
        db.commit()
        activity_log_service.log_event(
            db=db,
            event_type="workflow_retry_scheduled",
            entity_type="workflow",
            entity_id=workflow_id,
            details={"error": str(error), "retry_count": retries + 1},
        )
        # Signal to the Celery wrapper to actually retry.
        raise error

    workflow.status = WorkflowStatus.FAILED
    workflow.execution_logs = {"error": str(error), "final_failure": True}
    db.commit()
    activity_log_service.log_event(
        db=db,
        event_type="workflow_failed",
        entity_type="workflow",
        entity_id=workflow_id,
        details={"error": str(error)},
    )
    return {"error": str(error)}


@celery_app.task(
    bind=True,
    name="app.workers.tasks.execute_workflow_task",
    max_retries=3,
    default_retry_delay=60,
)
def execute_workflow_task(self, workflow_id: int) -> dict[str, Any]:
    """Celery wrapper around :func:`run_workflow_execution`."""
    try:
        return run_workflow_execution(
            workflow_id=workflow_id,
            task_id=self.request.id,
            retries=self.request.retries,
            max_retries=self.max_retries,
        )
    except Exception as exc:
        # ``run_workflow_execution`` re-raises only when we should retry.
        raise self.retry(exc=exc) from exc
