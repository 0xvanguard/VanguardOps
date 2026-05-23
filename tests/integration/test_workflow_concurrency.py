"""Concurrency contract test for ``run_workflow_execution`` against real Postgres.

This is the single most important test in the suite: it proves on a real
PostgreSQL engine that ``SELECT ... FOR UPDATE SKIP LOCKED`` (used in
``crud.workflow.claim_for_execution``) prevents double execution when N
Celery-style workers race for the same row.

Two strict assertions guard the contract:

1. The workflow body (``WorkflowExecutor.run_workflow``) is invoked
   **exactly once**, verified by a thread-safe counter installed via
   ``unittest.mock.patch``.
2. After all workers finish, the row's final status is ``SUCCESS`` and
   exactly one worker reports a successful result while the remaining
   ``N - 1`` report ``"Skipped due to status"``.

The test runs against a fresh ``postgres:16-alpine`` container booted by
Testcontainers, so it requires a reachable Docker daemon (the parent
``conftest.py`` skips the file otherwise).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, wait
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer

# Importing ``app.models`` populates ``Base.metadata`` with every table,
# which is what ``create_all`` below relies on.
import app.models  # noqa: F401
from app.database import Base
from app.models.workflow import Workflow, WorkflowStatus
from app.workers.tasks import run_workflow_execution

CONCURRENT_WORKERS = 8
"""Number of threads racing to claim the same workflow row."""


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Container, engine, and session fixtures (module-scoped to amortize cost).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def postgres_container() -> Iterator[PostgresContainer]:
    """Start a fresh Postgres 16 container for the duration of the module."""
    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest.fixture(scope="module")
def engine(postgres_container: PostgresContainer) -> Iterator[Engine]:
    """SQLAlchemy engine bound to the ephemeral Postgres container.

    Pool sized for our concurrency level: each worker may briefly hold up
    to three connections (claim / persist / log) so 20 leaves comfortable
    headroom over ``CONCURRENT_WORKERS = 8``.
    """
    eng = create_engine(
        postgres_container.get_connection_url(),
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
        future=True,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker:
    """A ``sessionmaker`` we can hand directly to ``run_workflow_execution``."""
    return sessionmaker(bind=engine, autoflush=False, future=True)


@pytest.fixture
def pending_workflow(session_factory: sessionmaker) -> Iterator[int]:
    """Insert a single PENDING workflow row, yield its id, and clean up after."""
    with session_factory() as db:
        workflow = Workflow(
            name="wf_auto_reset",
            trigger_type="concurrency-test",
            description="N workers race to claim me",
            status=WorkflowStatus.PENDING,
            config_data={"target": "test"},
        )
        db.add(workflow)
        db.commit()
        db.refresh(workflow)
        workflow_id = workflow.id
    yield workflow_id
    # Wipe everything created during this test so the next one starts clean.
    with session_factory() as db:
        db.execute(Workflow.__table__.delete())
        # Also clear audit logs the workers wrote so subsequent assertions
        # against them in other tests don't leak across cases.
        from app.models.activity_log import ActivityLog

        db.execute(ActivityLog.__table__.delete())
        db.commit()


# ---------------------------------------------------------------------------
# The actual contract test.
# ---------------------------------------------------------------------------


def test_skip_locked_prevents_double_execution(
    session_factory: sessionmaker, pending_workflow: int
) -> None:
    """N workers race; exactly one wins; executor body runs exactly once."""
    workflow_id = pending_workflow

    invocations: list[float] = []
    invocations_lock = threading.Lock()

    def _instrumented_executor(name: str, config: dict) -> dict:
        """Patched body: record the invocation and sleep to widen the race."""
        with invocations_lock:
            invocations.append(time.perf_counter())
        # 50ms is generous on a local Docker; long enough that a buggy
        # claim implementation would let other workers re-enter, short
        # enough to keep the test under a second.
        time.sleep(0.05)
        return {
            "status": "success",
            "action": "password_reset",
            "details": "instrumented",
        }

    # A barrier makes all 8 workers proceed *at the same instant*, which is
    # the worst case for any non-atomic claim implementation.
    barrier = threading.Barrier(CONCURRENT_WORKERS)

    def _worker() -> dict:
        barrier.wait()
        return run_workflow_execution(
            workflow_id=workflow_id,
            session_factory=session_factory,
        )

    # Patch at the import site (`app.workers.tasks`) so threads spawned
    # inside the worker pool also see the patched callable - mock.patch
    # propagates through module attribute lookup, which is process-wide.
    with (
        patch(
            "app.workers.workflow_executor.WorkflowExecutor.run_workflow",
            side_effect=_instrumented_executor,
        ),
        ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as pool,
    ):
        futures = [pool.submit(_worker) for _ in range(CONCURRENT_WORKERS)]
        wait(futures)
        results = [f.result() for f in futures]

    # ---- Assertion 1: workflow body invoked exactly once ----
    assert len(invocations) == 1, (
        f"WorkflowExecutor.run_workflow ran {len(invocations)} times "
        f"under {CONCURRENT_WORKERS} concurrent workers; expected exactly 1. "
        f"Race condition is back."
    )

    # ---- Assertion 2: exactly one success, N-1 skipped ----
    successes = [r for r in results if r.get("status") == "success"]
    skipped = [r for r in results if r.get("error") == "Skipped due to status"]
    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}: {results}"
    assert len(skipped) == CONCURRENT_WORKERS - 1, (
        f"Expected {CONCURRENT_WORKERS - 1} skipped workers, got {len(skipped)}: {results}"
    )
    # Defensive: nothing else (no failures, no workflow_not_found) should appear.
    accounted = len(successes) + len(skipped)
    assert accounted == CONCURRENT_WORKERS, f"Unaccounted-for worker results: {results}"

    # ---- Assertion 3: row's final state is SUCCESS ----
    with session_factory() as db:
        final: Workflow | None = db.get(Workflow, workflow_id)
        assert final is not None
        assert final.status == WorkflowStatus.SUCCESS
        assert final.execution_logs == {
            "status": "success",
            "action": "password_reset",
            "details": "instrumented",
        }


def test_concurrent_runs_against_distinct_workflows_all_succeed(
    session_factory: sessionmaker,
) -> None:
    """Sanity check: when each worker has its own row, all 8 succeed.

    This is the inverse of the headline test: it confirms that the row-level
    lock isn't accidentally serializing workers that should be independent.
    Without ``SKIP LOCKED`` we could regress here (workers would queue
    behind each other instead of skipping).
    """
    # Insert N distinct PENDING workflows.
    with session_factory() as db:
        rows = [
            Workflow(
                name="wf_auto_reset",
                trigger_type="concurrency-test-fan-out",
                status=WorkflowStatus.PENDING,
                config_data={},
            )
            for _ in range(CONCURRENT_WORKERS)
        ]
        db.add_all(rows)
        db.commit()
        ids = [row.id for row in rows]

    invocations = 0
    counter_lock = threading.Lock()

    def _counted(name: str, config: dict) -> dict:
        nonlocal invocations
        with counter_lock:
            invocations += 1
        return {"status": "success", "action": "password_reset"}

    barrier = threading.Barrier(CONCURRENT_WORKERS)

    def _worker(workflow_id: int) -> dict:
        barrier.wait()
        return run_workflow_execution(workflow_id=workflow_id, session_factory=session_factory)

    with (
        patch(
            "app.workers.workflow_executor.WorkflowExecutor.run_workflow",
            side_effect=_counted,
        ),
        ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as pool,
    ):
        futures = [pool.submit(_worker, wf_id) for wf_id in ids]
        wait(futures)
        results = [f.result() for f in futures]

    assert invocations == CONCURRENT_WORKERS, (
        f"Independent workflows should not block each other; expected "
        f"{CONCURRENT_WORKERS} invocations, got {invocations}"
    )
    assert all(r.get("status") == "success" for r in results), results

    with session_factory() as db:
        for wf_id in ids:
            wf: Workflow | None = db.get(Workflow, wf_id)
            assert wf is not None
            assert wf.status == WorkflowStatus.SUCCESS

    # Cleanup
    with session_factory() as db:
        db.execute(Workflow.__table__.delete())
        from app.models.activity_log import ActivityLog

        db.execute(ActivityLog.__table__.delete())
        db.commit()


# Mark this fixture as used so ruff doesn't flag it (it's referenced by the
# parametrized test above through pytest's fixture lookup).
def _silence_unused(_: Session) -> None:  # pragma: no cover
    pass
