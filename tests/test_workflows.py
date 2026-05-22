def test_create_workflow_unauthorized(client):
    response = client.post("/api/v1/workflows/", json={"name": "Test Workflow", "trigger_type": "manual"})
    assert response.status_code == 403

def test_create_workflow_authorized(client, admin_headers):
    response = client.post("/api/v1/workflows/", json={"name": "Test Workflow", "trigger_type": "manual"}, headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Workflow"
    assert "id" in data

def test_read_workflows(client):
    response = client.get("/api/v1/workflows/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0

def test_read_workflow_not_found(client):
    response = client.get("/api/v1/workflows/999")
    assert response.status_code == 404
