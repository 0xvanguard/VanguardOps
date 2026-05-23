"""Celery tasks.

Architecture (production-grade)
-------------------------------
Each task uses a **dedicated, per-invocation** SQLAlchemy session that is
guaranteed to be closed even if Celery itself fails midway (signal during
ack, lost connection to the broker, OOM kill mid-run, etc.). We achieve
that via the standard ``with SessionLocal() as db:`` context manager, which
calls ``Session.close()`` on ``__exit__`` regardless of what happened.

The task is split into two layers:

* ``run_workflow_execution`` is a *pure* function that takes a session
  factory (so tests can inject one) and returns a JSON-serializable dict.
  It contains no Celery state; it is therefore unit-testable without a
  broker.
* ``execute_workflow_task`` is the thin Celery decorator that translates
  retries into ``self.retry(...)``.

Concurrency model
-----------------
The PENDING/RETRYING -> RUNNING transition is performed by
``crud.workflow.claim_for_execution`` using ``SELECT ... FOR UPDATE SKIP
LOCKED`` (see that function's docstring). The lock is held for the
duration of the *claim* transaction only; workflow execution runs without
holding any DB lock, so a long workflow does not block other workers from
claiming other rows.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session

from app import crud
from app.core.logging import get_logger
from app.database import SessionLocal
from app.models.workflow import TERMINAL_WORKFLOW_STATUSES, Workflow, WorkflowStatus
from app.services.activity_log_service import activity_log_service
from app.workers.celery_app import celery_app
from app.workers.workflow_executor import WorkflowExecutor

logger = get_logger(__name__)


SessionFactory = Callable[[], Session]


@contextmanager
def _session_scope(factory: SessionFactory):
    """Yield a Session using the given factory and guarantee close on exit.

    A thin wrapper that lets us use a ``with`` block when the factory
    returns a session that is *not itself* a context manager (e.g. test
    fixtures that proxy a long-lived session).
    """
    session = factory()
    try:
        yield session
    finally:
        session.close()


def run_workflow_execution(
    workflow_id: int,
    *,
    session_factory: SessionFactory | None = None,
    task_id: str | None = None,
    retries: int = 0,
    max_retries: int = 0,
) -> dict[str, Any]:
    """Execute a single workflow run.

    Returns a JSON-serializable dict. Re-raises only when the Celery
    wrapper should perform a retry (the wrapper catches and calls
    ``self.retry``).
    """
    factory: SessionFactory = session_factory or SessionLocal

    # ---------- Phase 1: claim the row (short transaction, holds row lock) -
    with _session_scope(factory) as db:
        try:
            claimed = crud.workflow.claim_for_execution(db=db, workflow_id=workflow_id)
        except Exception:
            db.rollback()
            raise

        if claimed is None:
            # Could be: missing, locked by peer, or in a non-claimable status.
            # Disambiguate without taking any lock so we can produce a useful
            # audit log entry.
            actual = db.get(Workflow, workflow_id)
            if actual is None:
                logger.warning("workflow_not_found", workflow_id=workflow_id)
                return {"error": "workflow_not_found", "workflow_id": workflow_id}

            activity_log_service.log_event(
                db=db,
                event_type="workflow_skipped_duplicate",
                entity_type="workflow",
                entity_id=workflow_id,
                details={
                    "current_status": actual.status.value,
                    "reason": "row not in PENDING/RETRYING or held by another worker",
                },
            )
            return {
                "error": "Skipped due to status",
                "current_status": actual.status.value,
            }

        # Capture what we need *before* leaving the session boundary so we
        # don't accidentally use a detached instance later.
        workflow_name = claimed.name
        workflow_config = dict(claimed.config_data or {})

        activity_log_service.log_event(
            db=db,
            event_type="workflow_started",
            entity_type="workflow",
            entity_id=workflow_id,
            details={"worker_task_id": task_id},
        )

    # ---------- Phase 2: run the workflow body (no DB lock held) -----------
    try:
        result = WorkflowExecutor.run_workflow(workflow_name, workflow_config)
    except Exception as exec_error:
        with _session_scope(factory) as db:
            return _handle_failure(
                db=db,
                workflow_id=workflow_id,
                error=exec_error,
                retries=retries,
                max_retries=max_retries,
            )

    # ---------- Phase 3: persist success ----------------------------------
    with _session_scope(factory) as db:
        wf = db.get(Workflow, workflow_id)
        if wf is None:
            # Should not happen: row was deleted between phase 1 and 3.
            logger.error("workflow_disappeared_during_run", workflow_id=workflow_id)
            return {"error": "workflow_disappeared", "workflow_id": workflow_id}

        wf.status = WorkflowStatus.SUCCESS
        wf.execution_logs = result
        db.commit()

        activity_log_service.log_event(
            db=db,
            event_type="workflow_succeeded",
            entity_type="workflow",
            entity_id=workflow_id,
            details={"result": result},
        )
    return result


def _handle_failure(
    *,
    db: Session,
    workflow_id: int,
    error: Exception,
    retries: int,
    max_retries: int,
) -> dict[str, Any]:
    """Mark the workflow as RETRYING (and re-raise) or FAILED."""
    db.rollback()
    workflow = db.get(Workflow, workflow_id)
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
        # Signal to the Celery wrapper that we want a retry.
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
    acks_late=True,
)
def execute_workflow_task(self, workflow_id: int) -> dict[str, Any]:
    """Celery wrapper around :func:`run_workflow_execution`.

    The wrapper is intentionally minimal: it forwards the Celery context
    (task id, retry count, max retries) to the pure function and converts
    re-raised exceptions into ``self.retry()`` so the broker can re-deliver
    the task after ``default_retry_delay`` seconds.
    """
    try:
        return run_workflow_execution(
            workflow_id=workflow_id,
            task_id=self.request.id,
            retries=self.request.retries,
            max_retries=self.max_retries,
        )
    except Exception as exc:
        raise self.retry(exc=exc) from exc
