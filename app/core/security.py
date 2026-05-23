"""Cryptographic primitives and JWT helpers used across the application.

This module is intentionally framework-agnostic: it does *not* import from
FastAPI. The dependency wiring (``Depends``) lives in ``app.api.deps``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings
from app.core.exceptions import InvalidCredentialsError

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


class Role(StrEnum):
    """Application roles, ordered by privilege.

    ``ADMIN`` may perform every action (including managing users).
    ``OPERATOR`` may create/update tickets, assets and workflows.
    ``VIEWER`` is read-only.
    """

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


# ---------------------------------------------------------------------------
# Password hashing (bcrypt via passlib)
# ---------------------------------------------------------------------------

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hash a plain-text password using bcrypt with a per-call salt."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verification of a plaintext password against its hash."""
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        # Malformed hash, version mismatch, etc. - treat as failed auth.
        return False


# ---------------------------------------------------------------------------
# JWT issuance / verification
# ---------------------------------------------------------------------------


class TokenPayload(BaseModel):
    """Decoded JWT claims as exchanged across the API."""

    model_config = ConfigDict(extra="ignore")

    sub: str  # subject = user id (stringified)
    role: Role
    type: str  # "access" | "refresh"
    exp: int
    iat: int
    jti: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _build_token(
    *,
    subject: str,
    role: Role,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    now = _now()
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role.value,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "iss": settings.PROJECT_NAME,
        # ``jti`` (JWT ID) guarantees every issued token is unique even when
        # multiple tokens are minted within the same second; required for
        # blacklist support and useful for log correlation.
        "jti": uuid.uuid4().hex,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(
    *,
    subject: str | int,
    role: Role,
    expires_minutes: int | None = None,
) -> str:
    """Issue a short-lived access token."""
    settings = get_settings()
    delta = timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return _build_token(
        subject=str(subject),
        role=role,
        token_type="access",
        expires_delta=delta,
    )


def create_refresh_token(
    *,
    subject: str | int,
    role: Role,
    expires_days: int | None = None,
) -> str:
    """Issue a long-lived refresh token."""
    settings = get_settings()
    delta = timedelta(days=expires_days or settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return _build_token(
        subject=str(subject),
        role=role,
        token_type="refresh",
        expires_delta=delta,
    )


def decode_token(token: str, *, expected_type: str | None = None) -> TokenPayload:
    """Decode and validate a JWT.

    Verification order, fastest-first:

    1. **Signature + structural decode** (jwt.decode): rejects malformed,
       unsigned, or tampered tokens before we touch any external service.
    2. **Token-type check**: rejects access-where-refresh-was-expected,
       free of cost.
    3. **Blacklist lookup** (Redis ``/2``): rejects revoked tokens. See
       :mod:`app.services.token_blacklist` and ADR-007 for the
       fail-closed semantics when Redis is unreachable.

    Raises :class:`InvalidCredentialsError` on any failure so the caller
    can bubble the problem to the HTTP layer with a single ``except``.
    """
    settings = get_settings()
    try:
        raw = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise InvalidCredentialsError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise InvalidCredentialsError("Invalid authentication token") from exc

    payload = TokenPayload(**raw)
    if expected_type is not None and payload.type != expected_type:
        raise InvalidCredentialsError(
            f"Expected a '{expected_type}' token but received '{payload.type}'"
        )

    # Blacklist check (after signature so we never look up an unverified jti).
    # Lazy import keeps ``app.core.security`` import-safe even when the
    # token-blacklist module fails to load (e.g. during partial dev setup).
    if payload.jti:
        from app.services.token_blacklist import get_blacklist

        if get_blacklist().is_revoked(payload.jti):
            raise InvalidCredentialsError("Token has been revoked")

    return payload


# ---------------------------------------------------------------------------
# Role hierarchy helper
# ---------------------------------------------------------------------------

_ROLE_RANK: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.OPERATOR: 1,
    Role.ADMIN: 2,
}


def role_at_least(actual: Role, required: Role) -> bool:
    """Return ``True`` iff ``actual`` has at least ``required`` privileges."""
    return _ROLE_RANK[actual] >= _ROLE_RANK[required]
