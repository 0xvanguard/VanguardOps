"""Workflow execution tests (Celery task in eager mode + race conditions)."""

from __future__ import annotations

from app.models.workflow import Workflow, WorkflowStatus
from app.workers.tasks import run_workflow_execution
from tests.factories import WorkflowFactory


class _NoCloseSession:
    """Wrap a session so that the worker's ``db.close()`` is a no-op.

    The transactional test fixture owns the session lifecycle; the worker
    must not close it out from under the test runner.
    """

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def close(self) -> None:  # noqa: D401 - intentional no-op
        pass


def _factory(db_session):
    return lambda: _NoCloseSession(db_session)


def test_execution_success_path(client, operator_headers, db_session):
    workflow = WorkflowFactory(name="wf_auto_reset", status="PENDING")
    workflow_id = workflow.id

    result = run_workflow_execution(
        workflow_id=workflow_id,
        session_factory=_factory(db_session),
    )
    assert result.get("status") == "success"
    assert result["action"] == "password_reset"

    fresh = db_session.get(Workflow, workflow_id)
    assert fresh is not None
    assert fresh.status == WorkflowStatus.SUCCESS

    log_response = client.get(
        f"/api/v1/activity-log/workflow/{workflow_id}",
        headers=operator_headers,
    )
    events = {entry["event_type"] for entry in log_response.json()}
    assert "workflow_started" in events
    assert "workflow_succeeded" in events


def test_execution_skipped_when_already_terminal(client, operator_headers, db_session):
    workflow = WorkflowFactory(name="wf_ping_trace", status="PENDING")
    workflow_id = workflow.id

    # First run: success.
    run_workflow_execution(workflow_id=workflow_id, session_factory=_factory(db_session))
    fresh = db_session.get(Workflow, workflow_id)
    assert fresh.status == WorkflowStatus.SUCCESS

    # Second run: must be skipped because the row is no longer claimable.
    result = run_workflow_execution(workflow_id=workflow_id, session_factory=_factory(db_session))
    assert result.get("error") == "Skipped due to status"

    log_response = client.get(
        f"/api/v1/activity-log/workflow/{workflow_id}",
        headers=operator_headers,
    )
    events = {entry["event_type"] for entry in log_response.json()}
    assert "workflow_skipped_duplicate" in events


def test_execution_unknown_workflow():
    result = run_workflow_execution(workflow_id=999_999)
    assert result == {"error": "workflow_not_found", "workflow_id": 999_999}


def test_executor_marks_failed_on_unknown_name(db_session):
    workflow = WorkflowFactory(name="wf_does_not_exist", status="PENDING")
    workflow_id = workflow.id

    result = run_workflow_execution(workflow_id=workflow_id, session_factory=_factory(db_session))
    assert "error" in result

    fresh = db_session.get(Workflow, workflow_id)
    assert fresh.status == WorkflowStatus.FAILED
