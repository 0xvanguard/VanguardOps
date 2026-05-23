"""Regression tests for the security hardening wave.

These guard against the legacy ``X-Admin-Token`` re-entering the codebase
(see ADR-003) and lock in the JWT contract: every issued token must carry
``exp`` and ``jti``, and the OAuth2 scheme must advertise the form-encoded
``tokenUrl`` that the Swagger 'Authorize' button expects.
"""

from __future__ import annotations

import jwt
import pytest

from app.api.deps import oauth2_scheme
from app.core.config import Settings, get_settings
from app.core.security import Role, create_access_token, decode_token


def test_legacy_admin_token_header_is_not_accepted(client):
    """The pre-2.0 ``X-Admin-Token: super-secret-admin-token`` MUST NOT auth."""
    headers = {"X-Admin-Token": "super-secret-admin-token"}
    response = client.post(
        "/api/v1/tickets/",
        headers=headers,
        json={"title": "x", "description": "y", "severity": "MEDIUM"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


def test_arbitrary_bearer_string_is_rejected(client):
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer super-secret-admin-token"},
    )
    assert response.status_code == 401


def test_jwt_payload_includes_exp_and_jti():
    settings = get_settings()
    token = create_access_token(subject=1, role=Role.ADMIN)
    raw = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    assert "exp" in raw
    assert "iat" in raw
    assert "jti" in raw
    assert len(raw["jti"]) >= 16
    assert raw["type"] == "access"
    assert raw["iss"] == settings.PROJECT_NAME


def test_two_tokens_in_same_second_have_different_jti():
    a = create_access_token(subject=1, role=Role.ADMIN)
    b = create_access_token(subject=1, role=Role.ADMIN)
    payload_a = decode_token(a, expected_type="access")
    payload_b = decode_token(b, expected_type="access")
    assert payload_a.jti != payload_b.jti


def test_oauth2_scheme_points_to_form_endpoint():
    # The ``tokenUrl`` must be the form-encoded login so OAuth2PasswordBearer
    # can drive the Swagger Authorize flow correctly.
    flow = oauth2_scheme.model.flows.password
    assert flow.tokenUrl.endswith("/auth/login/oauth")


def test_production_rejects_dev_default_secret_key(monkeypatch):
    """Loading Settings with ENVIRONMENT=production must fail if the dev key is used."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "dev-only-secret-change-me-in-production-min-32-characters")
    with pytest.raises(Exception) as exc_info:
        Settings()
    msg = str(exc_info.value)
    assert "production" in msg.lower() or "secret_key" in msg.lower()


def test_password_hashes_are_unique_per_call():
    from app.core.security import hash_password, verify_password

    h1 = hash_password("CorrectHorseBatteryStaple")
    h2 = hash_password("CorrectHorseBatteryStaple")
    assert h1 != h2  # bcrypt salts make every hash unique
    assert verify_password("CorrectHorseBatteryStaple", h1)
    assert verify_password("CorrectHorseBatteryStaple", h2)
