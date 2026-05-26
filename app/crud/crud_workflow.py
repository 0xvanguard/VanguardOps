"""Workflow CRUD operations with row-level locking for concurrent workers.

Locking strategy
----------------
All claim operations use ``SELECT ... FOR UPDATE SKIP LOCKED`` which on
PostgreSQL provides true row-level pessimistic locking.  On SQLite the
clause is silently ignored; use SQLite only in single-worker test setups.

Lifecycle methods
-----------------
* :meth:`claim_for_execution`  — claim a specific row by *id* (direct dispatch).
* :meth:`claim_next_pending`   — pull the next available row from the queue
                                  ordered by priority + ``created_at``
                                  (worker loop, preferred pattern).
* :meth:`mark_succeeded`       — persist result payload and flip to SUCCESS.
* :meth:`mark_failed`          — handle retryable vs terminal failures with
                                  exponential backoff.
* :meth:`requeue_stale_running`— recover RUNNING rows whose worker died without
                                  finalising them (heartbeat-less safety net).
"""

from __future__ import annotations

import math
import socket
import threading
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.workflow import (
    TERMINAL_WORKFLOW_STATUSES,
    Workflow,
    WorkflowStatus,
)
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate

# Maximum number of automatic retries before a workflow is permanently failed.
MAX_ATTEMPTS: int = 3

# Base delay for exponential back-off: attempt_count is the exponent.
RETRY_BASE_SECONDS: float = 30.0

# How long a RUNNING row must be idle (no heartbeat / no completion) before it
# is considered stale and eligible for requeue.
STALE_RUNNING_TIMEOUT: timedelta = timedelta(minutes=10)


def _worker_id() -> str:
    """Return a stable, cheap worker identity string for *claimed_by*."""
    return f"{socket.gethostname()}:{threading.get_ident()}"


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _backoff_delay(attempt: int) -> timedelta:
    """Exponential back-off: 30s, 60s, 120s, … capped at 10 min."""
    seconds = min(RETRY_BASE_SECONDS * math.pow(2, attempt - 1), 600)
    return timedelta(seconds=seconds)


class CRUDWorkflow(CRUDBase[Workflow, WorkflowCreate, WorkflowUpdate]):
    # ------------------------------------------------------------------ #
    # Read helpers                                                         #
    # ------------------------------------------------------------------ #

    def get_by_ticket(
        self, db: Session, *, ticket_id: int, skip: int = 0, limit: int = 100
    ) -> Sequence[Workflow]:
        stmt = (
            select(Workflow)
            .where(Workflow.ticket_id == ticket_id)
            .offset(skip)
            .limit(limit)
        )
        return db.execute(stmt).scalars().all()

    def get_by_status(
        self,
        db: Session,
        *,
        status: WorkflowStatus,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Workflow]:
        stmt = (
            select(Workflow)
            .where(Workflow.status == status)
            .offset(skip)
            .limit(limit)
        )
        return db.execute(stmt).scalars().all()

    # ------------------------------------------------------------------ #
    # Claim operations                                                     #
    # ------------------------------------------------------------------ #

    def claim_for_execution(
        self, db: Session, *, workflow_id: int, worker_id: str | None = None
    ) -> Workflow | None:
        """Pessimistically claim a specific workflow row by *id*.

        Returns ``None`` when:

        * the row does not exist,
        * the row is in a non-claimable status (terminal or already RUNNING),
        * ``next_retry_at`` is in the future (back-off window not elapsed),
        * the row is locked by another worker (``SKIP LOCKED``).

        On success the row is transitioned to ``RUNNING`` and the transaction
        is committed, releasing the row-level lock so the (potentially long)
        execution body runs outside the lock scope.
        """
        now = _now_utc()
        stmt = (
            select(Workflow)
            .where(
                Workflow.id == workflow_id,
                Workflow.status.in_(
                    [WorkflowStatus.PENDING, WorkflowStatus.RETRYING]
                ),
                # Respect back-off: skip rows not yet ready for retry.
                (Workflow.next_retry_at.is_(None) | (Workflow.next_retry_at <= now)),
            )
            .with_for_update(skip_locked=True)
        )
        workflow = db.execute(stmt).scalar_one_or_none()
        if workflow is None:
            db.rollback()
            return None

        workflow.status = WorkflowStatus.RUNNING
        workflow.claimed_at = now
        workflow.claimed_by = worker_id or _worker_id()
        workflow.attempt_count = (workflow.attempt_count or 0) + 1
        workflow.error_detail = None  # clear previous transient error on new attempt
        db.commit()
        return workflow

    def claim_next_pending(
        self,
        db: Session,
        *,
        worker_id: str | None = None,
        limit: int = 1,
    ) -> Sequence[Workflow]:
        """Pull up to *limit* claimable rows from the queue.

        Ordering policy: ``next_retry_at ASC NULLS FIRST, created_at ASC``
        gives FIFO within each priority tier while respecting back-off delays.
        This is the preferred pattern for worker loops — it avoids the caller
        needing to know concrete workflow IDs.

        Rows locked by other workers are transparently skipped (SKIP LOCKED),
        so multiple workers calling this concurrently each get distinct rows
        with no coordination overhead.
        """
        now = _now_utc()
        stmt = (
            select(Workflow)
            .where(
                Workflow.status.in_(
                    [WorkflowStatus.PENDING, WorkflowStatus.RETRYING]
                ),
                (Workflow.next_retry_at.is_(None) | (Workflow.next_retry_at <= now)),
            )
            .order_by(
                # Rows with explicit retry times go first (they've waited).
                Workflow.next_retry_at.asc().nullsfirst(),
                Workflow.created_at.asc(),
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        workflows = list(db.execute(stmt).scalars().all())
        if not workflows:
            db.rollback()
            return []

        wid = worker_id or _worker_id()
        now_ts = now
        for wf in workflows:
            wf.status = WorkflowStatus.RUNNING
            wf.claimed_at = now_ts
            wf.claimed_by = wid
            wf.attempt_count = (wf.attempt_count or 0) + 1
            wf.error_detail = None

        db.commit()
        return workflows

    # ------------------------------------------------------------------ #
    # Terminal transitions                                                 #
    # ------------------------------------------------------------------ #

    def mark_succeeded(
        self,
        db: Session,
        *,
        workflow_id: int,
        result_payload: dict[str, Any] | None = None,
    ) -> Workflow | None:
        """Transition a RUNNING workflow to SUCCESS and persist its result.

        ``execution_logs`` is merged (not replaced) so any pre-execution
        metadata written by the caller is preserved.  Returns ``None`` if the
        row no longer exists or is not in RUNNING state (defensive guard
        against double-completion).
        """
        workflow = db.get(Workflow, workflow_id)
        if workflow is None or workflow.status is not WorkflowStatus.RUNNING:
            return None

        workflow.status = WorkflowStatus.SUCCESS
        workflow.error_detail = None
        workflow.next_retry_at = None

        if result_payload is not None:
            existing = workflow.execution_logs or {}
            workflow.execution_logs = {**existing, **result_payload}

        db.commit()
        db.refresh(workflow)
        return workflow

    def mark_failed(
        self,
        db: Session,
        *,
        workflow_id: int,
        error: str,
        retryable: bool = True,
        extra_logs: dict[str, Any] | None = None,
    ) -> Workflow | None:
        """Transition a RUNNING workflow to RETRYING or FAILED.

        If *retryable* is ``True`` **and** ``attempt_count < MAX_ATTEMPTS``,
        the row is moved to ``RETRYING`` and ``next_retry_at`` is set
        according to exponential back-off.  Otherwise it is permanently
        ``FAILED``.

        ``error`` is stored in ``error_detail`` for quick triage without
        parsing JSON logs.  ``extra_logs`` is shallow-merged into
        ``execution_logs`` to capture structured debug context.
        """
        workflow = db.get(Workflow, workflow_id)
        if workflow is None or workflow.status is not WorkflowStatus.RUNNING:
            return None

        workflow.error_detail = error

        if extra_logs:
            existing = workflow.execution_logs or {}
            workflow.execution_logs = {**existing, **extra_logs}

        exhausted = (workflow.attempt_count or 0) >= MAX_ATTEMPTS
        if retryable and not exhausted:
            workflow.status = WorkflowStatus.RETRYING
            workflow.next_retry_at = _now_utc() + _backoff_delay(
                workflow.attempt_count or 1
            )
        else:
            workflow.status = WorkflowStatus.FAILED
            workflow.next_retry_at = None

        db.commit()
        db.refresh(workflow)
        return workflow

    # ------------------------------------------------------------------ #
    # Stale-lock recovery                                                  #
    # ------------------------------------------------------------------ #

    def requeue_stale_running(
        self,
        db: Session,
        *,
        timeout: timedelta = STALE_RUNNING_TIMEOUT,
        limit: int = 50,
    ) -> int:
        """Requeue RUNNING rows whose worker has not completed within *timeout*.

        This is the heartbeat-less safety net: a maintenance task (cron,
        Celery beat) calls this periodically to recover orphaned workflows
        caused by worker crashes or deployment restarts.

        Returns the number of rows requeued.

        Decision logic
        ~~~~~~~~~~~~~~
        * ``attempt_count < MAX_ATTEMPTS``  → ``RETRYING`` + back-off
        * ``attempt_count >= MAX_ATTEMPTS`` → ``FAILED`` (permanently give up)

        The cutoff is ``claimed_at < now() - timeout``.  Rows with a NULL
        ``claimed_at`` (legacy data) also qualify.
        """
        now = _now_utc()
        cutoff = now - timeout

        stmt = (
            select(Workflow)
            .where(
                Workflow.status == WorkflowStatus.RUNNING,
                (Workflow.claimed_at.is_(None) | (Workflow.claimed_at < cutoff)),
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        stale = list(db.execute(stmt).scalars().all())
        if not stale:
            db.rollback()
            return 0

        for wf in stale:
            exhausted = (wf.attempt_count or 0) >= MAX_ATTEMPTS
            if exhausted:
                wf.status = WorkflowStatus.FAILED
                wf.error_detail = (
                    f"Permanently failed after {wf.attempt_count} attempts "
                    f"(stale lock recovery, timeout={timeout})."
                )
                wf.next_retry_at = None
            else:
                wf.status = WorkflowStatus.RETRYING
                wf.error_detail = (
                    f"Worker did not complete within {timeout}; "
                    f"requeued at attempt {wf.attempt_count}."
                )
                wf.next_retry_at = now + _backoff_delay(wf.attempt_count or 1)

        db.commit()
        return len(stale)


workflow = CRUDWorkflow(Workflow)
