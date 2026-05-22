def test_create_asset_unauthorized(client):
    response = client.post("/api/v1/assets/", json={"name": "Test Server", "asset_type": "SERVER", "status": "ACTIVE"})
    assert response.status_code == 403

def test_create_asset_authorized(client, admin_headers):
    response = client.post("/api/v1/assets/", json={"name": "Test Server", "asset_type": "SERVER", "status": "ACTIVE"}, headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Server"
    assert "id" in data

def test_read_assets(client):
    response = client.get("/api/v1/assets/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0

def test_read_asset_not_found(client):
    response = client.get("/api/v1/assets/999")
    assert response.status_code == 404
