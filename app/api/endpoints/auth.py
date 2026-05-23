"""Authentication endpoints: login, refresh, register, logout, ``/me``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import (
    CurrentUser,
    DbSession,
    require_admin,
)
from app.core.exceptions import InvalidCredentialsError
from app.core.security import Role, decode_token
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserRead,
)
from app.services.activity_log_service import activity_log_service
from app.services.auth_service import auth_service
from app.services.token_blacklist import get_blacklist

router = APIRouter()


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Exchange email + password for a JWT token pair",
)
def login(payload: LoginRequest, db: DbSession) -> TokenPair:
    user = auth_service.authenticate(db=db, email=payload.email, password=payload.password)
    return auth_service.issue_token_pair(user)


@router.post(
    "/login/oauth",
    response_model=TokenPair,
    summary="OAuth2-compatible login (form-encoded)",
    description=(
        "Accepts ``application/x-www-form-urlencoded`` with ``username`` "
        "(email) and ``password``. Useful for OpenAPI 'Authorize' button."
    ),
)
def login_oauth(
    db: DbSession,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> TokenPair:
    user = auth_service.authenticate(db=db, email=form_data.username, password=form_data.password)
    return auth_service.issue_token_pair(user)


@router.post(
    "/refresh", response_model=TokenPair, summary="Exchange a refresh token for a new pair"
)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    return auth_service.refresh_pair(db=db, refresh_token=payload.refresh_token)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
    summary="Register a new user (admin-only)",
)
def register(payload: UserCreate, db: DbSession) -> UserRead:
    """Only administrators may create users in this build.

    Self-signup is intentionally disabled to avoid privilege drift in a
    small operator-style platform.
    """
    user = auth_service.register(db=db, payload=payload, requesting_role=Role.ADMIN)
    return user  # type: ignore[return-value]


@router.get("/me", response_model=UserRead, summary="Return the current authenticated user")
def me(current: CurrentUser) -> UserRead:
    return current  # type: ignore[return-value]


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Revoke the current access token (and optionally a refresh token)",
)
def logout(
    request: Request,
    current: CurrentUser,
    db: DbSession,
    payload: LogoutRequest | None = None,
) -> dict:
    """Add the bearer token's ``jti`` to the Redis blacklist.

    Subsequent requests presenting the same token will receive
    ``401 invalid_credentials`` because :func:`decode_token` consults
    the blacklist on every decode (see ADR-007).

    Optionally accepts a ``refresh_token`` in the JSON body; when
    provided, its ``jti`` is also revoked. We refuse refresh tokens that
    do not belong to the authenticated user (defence against a stolen
    access token + arbitrary refresh-token revocation amplification
    attack).
    """
    blacklist = get_blacklist()
    revoked: list[str] = []

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        # Should be impossible because ``current`` already authenticated,
        # but we re-validate to keep the contract obvious to readers.
        raise InvalidCredentialsError("Missing bearer token in Authorization header")
    access_token = auth_header.removeprefix("Bearer ").strip()
    access_payload = decode_token(access_token, expected_type="access")
    blacklist.revoke(access_payload.jti or "", access_payload.exp)
    revoked.append(access_payload.jti or "")

    if payload is not None and payload.refresh_token:
        try:
            refresh_payload = decode_token(payload.refresh_token, expected_type="refresh")
        except InvalidCredentialsError:
            # Silently ignore an already-bad refresh token; the access
            # token is the authoritative session anchor and we revoked it.
            refresh_payload = None
        if refresh_payload is not None:
            if str(refresh_payload.sub) != str(current.id):
                raise InvalidCredentialsError(
                    "Refresh token does not belong to the authenticated user"
                )
            blacklist.revoke(refresh_payload.jti or "", refresh_payload.exp)
            revoked.append(refresh_payload.jti or "")

    activity_log_service.log_event(
        db=db,
        event_type="user_logged_out",
        entity_type="user",
        entity_id=current.id,
        actor_id=str(current.id),
        actor_type="user",
        details={"revoked_jtis": revoked},
    )
    return {"status": "logged_out", "revoked_jtis": revoked}
