"""Tests for password hashing, JWT issuance and decoding."""

from __future__ import annotations

import time

import pytest

from app.core.exceptions import InvalidCredentialsError
from app.core.security import (
    Role,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    role_at_least,
    verify_password,
)


def test_hash_and_verify_password_round_trip():
    h = hash_password("S3cret-Pwd!")
    assert verify_password("S3cret-Pwd!", h)
    assert not verify_password("wrong", h)


def test_hash_password_produces_unique_salts():
    assert hash_password("same") != hash_password("same")


def test_access_token_round_trip():
    token = create_access_token(subject=42, role=Role.ADMIN)
    payload = decode_token(token, expected_type="access")
    assert payload.sub == "42"
    assert payload.role == Role.ADMIN
    assert payload.type == "access"


def test_refresh_token_type_distinguishable():
    token = create_refresh_token(subject="7", role=Role.OPERATOR)
    payload = decode_token(token, expected_type="refresh")
    assert payload.type == "refresh"

    with pytest.raises(InvalidCredentialsError):
        decode_token(token, expected_type="access")


def test_decode_rejects_garbage():
    with pytest.raises(InvalidCredentialsError):
        decode_token("not-a-jwt")


def test_role_hierarchy():
    assert role_at_least(Role.ADMIN, Role.OPERATOR)
    assert role_at_least(Role.OPERATOR, Role.VIEWER)
    assert not role_at_least(Role.VIEWER, Role.OPERATOR)
    assert role_at_least(Role.ADMIN, Role.ADMIN)


def test_expired_token_is_rejected():
    # negative expiry => already expired
    token = create_access_token(subject="1", role=Role.VIEWER, expires_minutes=-1)
    time.sleep(0.05)
    with pytest.raises(InvalidCredentialsError):
        decode_token(token, expected_type="access")
