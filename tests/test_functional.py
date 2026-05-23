"""End-to-end functional scenarios.

These cover business journeys (asset → ticket → workflow → audit) rather
than individual endpoints.
"""

from __future__ import annotations


def test_scenario_full_password_reset_flow(client, operator_headers):
    # 1. Register an asset
    asset_resp = client.post(
        "/api/v1/assets/",
        headers=operator_headers,
        json={
            "name": "laptop-001",
            "asset_type": "WORKSTATION",
            "ip_address": "10.0.0.1",
        },
    )
    assert asset_resp.status_code == 201
    asset_id = asset_resp.json()["id"]

    # 2. Open a password-reset ticket against it
    ticket_resp = client.post(
        "/api/v1/tickets/",
        headers=operator_headers,
        json={
            "title": "Reset password",
            "description": "User locked out",
            "category": "password_reset",
            "severity": "MEDIUM",
            "asset_id": asset_id,
        },
    )
    assert ticket_resp.status_code == 201
    ticket = ticket_resp.json()
    assert ticket["priority"] == "MEDIUM"
    assert ticket["assigned_to"] == "L1_Service_Desk"

    # 3. Move it through the state machine: OPEN -> IN_PROGRESS -> RESOLVED
    for new_status in ("IN_PROGRESS", "RESOLVED"):
        upd = client.patch(
            f"/api/v1/tickets/{ticket['id']}",
            headers=operator_headers,
            json={"status": new_status},
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["status"] == new_status

    # 4. Audit log includes every event
    logs = client.get(
        f"/api/v1/activity-log/ticket/{ticket['id']}", headers=operator_headers
    ).json()
    events = {entry["event_type"] for entry in logs}
    assert {
        "ticket_created",
        "ticket_prioritized",
        "ticket_assigned",
        "workflow_triggered",
        "ticket_updated",
        "ticket_status_changed",
    } <= events


def test_scenario_security_ticket_no_workflow(client, operator_headers):
    response = client.post(
        "/api/v1/tickets/",
        headers=operator_headers,
        json={
            "title": "Ransomware",
            "description": "Critical incident",
            "category": "security",
            "severity": "CRITICAL",
        },
    )
    assert response.status_code == 201
    ticket = response.json()
    assert ticket["priority"] == "CRITICAL"
    assert ticket["assigned_to"] == "L3_Security_Ops"

    logs = client.get(
        f"/api/v1/activity-log/ticket/{ticket['id']}", headers=operator_headers
    ).json()
    events = {entry["event_type"] for entry in logs}
    assert "workflow_triggered" not in events


def test_scenario_unauthenticated_access_blocked(client):
    response = client.post(
        "/api/v1/tickets/",
        json={"title": "x", "description": "y", "severity": "LOW"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
