"""Asset endpoints."""

from __future__ import annotations

from tests.factories import AssetFactory


def test_create_asset_unauthenticated(client):
    response = client.post(
        "/api/v1/assets/",
        json={"name": "srv-1", "asset_type": "SERVER"},
    )
    assert response.status_code == 401


def test_create_asset_as_operator(client, operator_headers):
    response = client.post(
        "/api/v1/assets/",
        headers=operator_headers,
        json={
            "name": "srv-1",
            "asset_type": "SERVER",
            "status": "ACTIVE",
            "ip_address": "10.0.0.1",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "srv-1"
    assert body["ip_address"] == "10.0.0.1"


def test_create_asset_rejects_invalid_ip(client, operator_headers):
    response = client.post(
        "/api/v1/assets/",
        headers=operator_headers,
        json={"name": "bad", "asset_type": "SERVER", "ip_address": "not-an-ip"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"


def test_list_assets_paginated(client, viewer_headers, db_session):
    AssetFactory.create_batch(5)
    response = client.get("/api/v1/assets/?page=1&size=2", headers=viewer_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["size"] == 2
    assert body["has_next"] is True
    assert body["has_prev"] is False
    assert len(body["items"]) == 2


def test_get_asset_by_id(client, viewer_headers, db_session):
    asset = AssetFactory(name="db-master", ip_address="10.10.0.10")
    response = client.get(f"/api/v1/assets/{asset.id}", headers=viewer_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "db-master"


def test_get_asset_not_found(client, viewer_headers):
    response = client.get("/api/v1/assets/9999", headers=viewer_headers)
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "asset_not_found"


def test_get_asset_by_ip(client, viewer_headers, db_session):
    AssetFactory(ip_address="10.20.30.40", name="firewall")
    response = client.get("/api/v1/assets/by-ip/10.20.30.40", headers=viewer_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "firewall"


def test_update_asset(client, operator_headers, db_session):
    asset = AssetFactory(name="old", status="ACTIVE")
    response = client.patch(
        f"/api/v1/assets/{asset.id}",
        headers=operator_headers,
        json={"name": "new", "status": "MAINTENANCE"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "new"
    assert body["status"] == "MAINTENANCE"
