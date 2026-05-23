import pytest
from tests.conftest import client, admin_headers

# ESCENARIO A - Creación y Consulta de Activo
def test_escenario_a_assets(client, admin_headers):
    # Crear un asset válido
    res_create = client.post("/api/v1/assets/", json={"name": "Firewall Core", "asset_type": "NETWORK_DEVICE", "status": "ACTIVE", "ip_address": "192.168.1.1"}, headers=admin_headers)
    assert res_create.status_code == 200
    asset_id = res_create.json()["id"]

    # Consultarlo por ID
    res_get = client.get(f"/api/v1/assets/{asset_id}")
    assert res_get.status_code == 200
    assert res_get.json()["name"] == "Firewall Core"

    # Consultarlo por status
    res_status = client.get("/api/v1/assets/by-status/ACTIVE")
    assert res_status.status_code == 200
    assert len(res_status.json()) >= 1

    # Consultarlo por IP
    res_ip = client.get("/api/v1/assets/by-ip/192.168.1.1")
    assert res_ip.status_code == 200

# ESCENARIO B - Ticket Normal (Password Reset)
def test_escenario_b_ticket_normal(client, admin_headers):
    res = client.post("/api/v1/tickets/", json={
        "title": "Reset password",
        "description": "User locked out",
        "category": "password_reset",
        "severity": "MEDIUM"
    }, headers=admin_headers)
    assert res.status_code == 200
    ticket = res.json()
    
    assert ticket["priority"] == "MEDIUM"  # Auto priority
    assert ticket["assigned_to"] == "L1_Service_Desk"  # Auto assign
    assert ticket["due_at"] is not None  # SLA calculado
    
    # Validar logs
    log_res = client.get(f"/api/v1/activity-log/ticket/{ticket['id']}")
    logs = log_res.json()
    event_types = [log["event_type"] for log in logs]
    assert "ticket_created" in event_types
    assert "ticket_prioritized" in event_types
    assert "ticket_assigned" in event_types
    assert "workflow_triggered" in event_types  # wf_auto_reset

# ESCENARIO C - Ticket Crítico de Seguridad
def test_escenario_c_ticket_critico(client, admin_headers):
    res = client.post("/api/v1/tickets/", json={
        "title": "Ransomware alert",
        "description": "Multiple servers encrypted",
        "category": "security",
        "severity": "CRITICAL"
    }, headers=admin_headers)
    assert res.status_code == 200
    ticket = res.json()
    
    assert ticket["priority"] == "CRITICAL"
    assert ticket["assigned_to"] == "L3_Security_Ops"
    
    log_res = client.get(f"/api/v1/activity-log/ticket/{ticket['id']}")
    logs = log_res.json()
    event_types = [log["event_type"] for log in logs]
    assert "workflow_triggered" not in event_types # No hay WF para security yet

# ESCENARIO D - Actualización de Ticket
def test_escenario_d_update_ticket(client, admin_headers):
    # Asume que test C creó el id 2
    res_put = client.put("/api/v1/tickets/2", json={"status": "IN_PROGRESS"}, headers=admin_headers)
    assert res_put.status_code == 200
    assert res_put.json()["status"] == "IN_PROGRESS"
    
    log_res = client.get("/api/v1/activity-log/ticket/2")
    event_types = [log["event_type"] for log in log_res.json()]
    assert "ticket_updated" in event_types

# ESCENARIO F - Seguridad y Edge Cases
def test_escenario_f_edge_cases(client):
    # Falla auth
    res_no_auth = client.post("/api/v1/tickets/", json={"title": "Test", "description": "Desc"})
    assert res_no_auth.status_code == 403
    
    # Asset Inexistente
    headers = {"X-Admin-Token": "super-secret-admin-token"}
    res_bad_asset = client.post("/api/v1/tickets/", json={"title": "Test", "description": "Desc", "asset_id": 99999}, headers=headers)
    assert res_bad_asset.status_code == 400
