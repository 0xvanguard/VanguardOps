"""Workflow endpoints."""

from __future__ import annotations

from tests.factories import WorkflowFactory


def test_create_workflow_requires_auth(client):
    response = client.post("/api/v1/workflows/", json={"name": "test", "trigger_type": "manual"})
    assert response.status_code == 401


def test_create_workflow_as_operator_starts_pending(client, operator_headers):
    response = client.post(
        "/api/v1/workflows/",
        headers=operator_headers,
        json={"name": "wf_auto_reset", "trigger_type": "manual"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["name"] == "wf_auto_reset"


def test_list_workflows_paginated(client, viewer_headers, db_session):
    WorkflowFactory.create_batch(3)
    response = client.get("/api/v1/workflows/", headers=viewer_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3


def test_get_workflow_not_found(client, viewer_headers):
    response = client.get("/api/v1/workflows/9999", headers=viewer_headers)
    assert response.status_code == 404
    assert response.json()["code"] == "workflow_not_found"


def test_filter_workflows_by_status(client, viewer_headers, db_session):
    WorkflowFactory(status="PENDING")
    WorkflowFactory(status="SUCCESS")
    response = client.get("/api/v1/workflows/by-status/PENDING", headers=viewer_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
