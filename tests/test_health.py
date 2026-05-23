"""Health, readiness and metrics endpoints."""

from __future__ import annotations


def test_legacy_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "VanguardOps" in body["service"]


def test_livez(client):
    response = client.get("/livez")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "VanguardOps"


def test_readyz_in_test_mode(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    # Redis (both broker and blacklist) is intentionally skipped in test mode.
    assert "redis_broker" not in body["checks"]
    assert "redis_blacklist" not in body["checks"]


def test_metrics_endpoint(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    text = response.text
    assert "http_requests_total" in text
    assert "http_request_duration_seconds" in text


def test_request_id_header_propagates(client):
    custom = "test-trace-id-123"
    response = client.get("/livez", headers={"X-Request-ID": custom})
    assert response.headers.get("X-Request-ID") == custom


def test_security_headers_present(client):
    response = client.get("/livez")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert "Referrer-Policy" in response.headers
