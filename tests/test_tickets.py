def test_create_ticket_unauthorized(client):
    response = client.post("/api/v1/tickets/", json={"title": "Test Ticket", "description": "Desc"})
    assert response.status_code == 403

def test_create_ticket_authorized(client, admin_headers):
    response = client.post("/api/v1/tickets/", json={"title": "Test Ticket", "description": "Desc"}, headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Ticket"
    assert "id" in data

def test_read_tickets(client):
    response = client.get("/api/v1/tickets/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0

def test_read_ticket_not_found(client):
    response = client.get("/api/v1/tickets/999")
    assert response.status_code == 404

def test_update_ticket_unauthorized(client):
    response = client.put("/api/v1/tickets/1", json={"title": "Updated"})
    assert response.status_code == 403

def test_update_ticket_authorized(client, admin_headers):
    # Asume que el ticket ID 1 ya fue creado en test_create_ticket_authorized
    response = client.put("/api/v1/tickets/1", json={"title": "Updated"}, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["title"] == "Updated"
