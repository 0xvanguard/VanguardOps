"""Authentication & RBAC tests."""

from __future__ import annotations

from app.core.security import Role
from tests.factories import UserFactory


def test_login_success_returns_token_pair(client, db_session):
    UserFactory(email="op@vanguardops.io", role=Role.OPERATOR)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "op@vanguardops.io", "password": "Test!2345"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] > 0


def test_login_invalid_password(client, db_session):
    UserFactory(email="op@vanguardops.io", role=Role.OPERATOR)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "op@vanguardops.io", "password": "wrong"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "invalid_credentials"
    assert body["status"] == 401


def test_login_unknown_user_returns_same_error(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@vanguardops.io", "password": "whatever"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


def test_refresh_endpoint_issues_new_pair(client, db_session):
    UserFactory(email="op@vanguardops.io", role=Role.OPERATOR)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "op@vanguardops.io", "password": "Test!2345"},
    ).json()
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] != login["access_token"]


def test_refresh_with_access_token_is_rejected(client, db_session):
    UserFactory(email="op@vanguardops.io", role=Role.OPERATOR)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "op@vanguardops.io", "password": "Test!2345"},
    ).json()
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["access_token"]},
    )
    assert response.status_code == 401


def test_me_returns_current_user(client, operator_headers, operator_user):
    response = client.get("/api/v1/auth/me", headers=operator_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == operator_user.email
    assert body["role"] == "operator"


def test_protected_route_without_token_returns_401(client):
    response = client.get("/api/v1/tickets/")
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


def test_viewer_cannot_create_ticket(client, viewer_headers):
    response = client.post(
        "/api/v1/tickets/",
        headers=viewer_headers,
        json={"title": "x", "description": "y", "severity": "MEDIUM"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_register_requires_admin(client, operator_headers):
    response = client.post(
        "/api/v1/auth/register",
        headers=operator_headers,
        json={
            "email": "new@vanguardops.io",
            "password": "Test!2345",
            "role": "operator",
        },
    )
    assert response.status_code == 403


def test_register_with_admin_creates_user(client, admin_headers):
    response = client.post(
        "/api/v1/auth/register",
        headers=admin_headers,
        json={
            "email": "new@vanguardops.io",
            "password": "Test!2345",
            "role": "operator",
            "full_name": "New User",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@vanguardops.io"
    assert body["role"] == "operator"


def test_register_duplicate_email_returns_409(client, admin_headers, db_session):
    UserFactory(email="dup@vanguardops.io")
    response = client.post(
        "/api/v1/auth/register",
        headers=admin_headers,
        json={
            "email": "dup@vanguardops.io",
            "password": "Test!2345",
            "role": "viewer",
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "user_already_exists"
