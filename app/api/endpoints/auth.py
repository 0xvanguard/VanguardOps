"""Authentication endpoints: login, refresh, register and ``/me``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import (
    CurrentUser,
    DbSession,
    require_admin,
)
from app.core.security import Role
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserRead,
)
from app.services.auth_service import auth_service

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
