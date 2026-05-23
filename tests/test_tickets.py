"""Ticket endpoints (creation, state machine, audit emission)."""

from __future__ import annotations

from tests.factories import AssetFactory, TicketFactory


def test_create_ticket_unauthenticated(client):
    response = client.post(
        "/api/v1/tickets/",
        json={"title": "x", "description": "y", "severity": "MEDIUM"},
    )
    assert response.status_code == 401


def test_create_ticket_normal_emits_full_audit(client, operator_headers):
    response = client.post(
        "/api/v1/tickets/",
        headers=operator_headers,
        json={
            "title": "Reset password",
            "description": "User locked out",
            "category": "password_reset",
            "severity": "MEDIUM",
        },
    )
    assert response.status_code == 201
    ticket = response.json()
    assert ticket["priority"] == "MEDIUM"
    assert ticket["assigned_to"] == "L1_Service_Desk"
    assert ticket["due_at"] is not None

    # Activity log: must contain creation, prioritization, assignment and
    # downstream workflow trigger.
    log_response = client.get(
        f"/api/v1/activity-log/ticket/{ticket['id']}", headers=operator_headers
    )
    assert log_response.status_code == 200
    events = {entry["event_type"] for entry in log_response.json()}
    assert {"ticket_created", "ticket_prioritized", "ticket_assigned"} <= events
    assert "workflow_triggered" in events


def test_create_critical_security_ticket(client, operator_headers):
    response = client.post(
        "/api/v1/tickets/",
        headers=operator_headers,
        json={
            "title": "Ransomware alert",
            "description": "Multiple servers encrypted",
            "category": "security",
            "severity": "CRITICAL",
        },
    )
    assert response.status_code == 201
    ticket = response.json()
    assert ticket["priority"] == "CRITICAL"
    assert ticket["assigned_to"] == "L3_Security_Ops"

    # No workflow auto-triggered for security category yet.
    log_response = client.get(
        f"/api/v1/activity-log/ticket/{ticket['id']}", headers=operator_headers
    )
    events = {entry["event_type"] for entry in log_response.json()}
    assert "workflow_triggered" not in events


def test_create_ticket_with_unknown_asset_returns_404(client, operator_headers):
    response = client.post(
        "/api/v1/tickets/",
        headers=operator_headers,
        json={
            "title": "x",
            "description": "y",
            "asset_id": 999_999,
            "severity": "MEDIUM",
        },
    )
    assert response.status_code == 404
    assert response.json()["code"] == "asset_not_found"


def test_create_ticket_with_existing_asset(client, operator_headers, db_session):
    asset = AssetFactory()
    response = client.post(
        "/api/v1/tickets/",
        headers=operator_headers,
        json={
            "title": "x",
            "description": "y",
            "asset_id": asset.id,
            "severity": "LOW",
        },
    )
    assert response.status_code == 201
    assert response.json()["asset_id"] == asset.id


def test_list_tickets_paginated(client, viewer_headers, db_session):
    TicketFactory.create_batch(3)
    response = client.get("/api/v1/tickets/?page=1&size=2", headers=viewer_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["has_next"] is True


def test_filter_tickets_by_status(client, viewer_headers, db_session):
    TicketFactory.create_batch(2, status="OPEN")
    TicketFactory(status="IN_PROGRESS")
    response = client.get("/api/v1/tickets/filter?status_value=OPEN", headers=viewer_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2


def test_update_ticket_valid_transition(client, operator_headers, db_session):
    ticket = TicketFactory(status="OPEN")
    response = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=operator_headers,
        json={"status": "IN_PROGRESS"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "IN_PROGRESS"

    log_response = client.get(f"/api/v1/activity-log/ticket/{ticket.id}", headers=operator_headers)
    events = {entry["event_type"] for entry in log_response.json()}
    assert "ticket_updated" in events
    assert "ticket_status_changed" in events


def test_update_ticket_invalid_transition_returns_409(client, operator_headers, db_session):
    ticket = TicketFactory(status="CLOSED")
    response = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=operator_headers,
        json={"status": "OPEN"},
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "invalid_state_transition"
    assert body["current_status"] == "CLOSED"


def test_get_ticket_not_found(client, viewer_headers):
    response = client.get("/api/v1/tickets/9999", headers=viewer_headers)
    assert response.status_code == 404
    assert response.json()["code"] == "ticket_not_found"
