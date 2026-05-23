"""FastAPI dependency wiring (DB sessions, current user, RBAC, pagination)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    ForbiddenError,
    InvalidCredentialsError,
)
from app.core.security import Role, decode_token, role_at_least
from app.database import SessionLocal
from app.models.user import User

# ---------------------------------------------------------------------------
# Database session
# ---------------------------------------------------------------------------


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# OAuth2 / JWT
# ---------------------------------------------------------------------------

_settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{_settings.API_V1_PREFIX}/auth/login",
    auto_error=False,
)


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: DbSession,
) -> User:
    """Decode the bearer token and return the active user behind it."""
    if not token:
        raise InvalidCredentialsError("Authentication credentials were not provided")
    payload = decode_token(token, expected_type="access")
    user = db.get(User, int(payload.sub))
    if user is None or not user.is_active:
        raise InvalidCredentialsError("User no longer exists or is disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(required: Role):
    """Build a dependency that enforces a minimum role for the route."""

    def _checker(current: CurrentUser) -> User:
        if not role_at_least(current.role, required):
            raise ForbiddenError(
                f"Role '{required.value}' or higher is required",
                extras={"required_role": required.value, "actual_role": current.role.value},
            )
        return current

    return _checker


# Convenience aliases for the common case.
require_admin = require_role(Role.ADMIN)
require_operator = require_role(Role.OPERATOR)
require_viewer = require_role(Role.VIEWER)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class PaginationParams(BaseModel):
    page: int = 1
    size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size


def pagination_params(
    page: int = Query(1, ge=1, description="1-based page number"),
    size: int = Query(20, ge=1, le=200, description="Items per page (max 200)"),
) -> PaginationParams:
    return PaginationParams(page=page, size=size)


PaginationDep = Annotated[PaginationParams, Depends(pagination_params)]
