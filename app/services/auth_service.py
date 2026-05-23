"""Authentication service: password verification + token issuance."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import crud
from app.core.config import get_settings
from app.core.exceptions import (
    InvalidCredentialsError,
    UserAlreadyExistsError,
)
from app.core.security import (
    Role,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenPair, UserCreate


class AuthService:
    @staticmethod
    def authenticate(db: Session, *, email: str, password: str) -> User:
        user = crud.user.get_by_email(db=db, email=email)
        if user is None or not user.is_active:
            # Same error message regardless to avoid user enumeration.
            raise InvalidCredentialsError("Invalid email or password")
        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Invalid email or password")
        return user

    @staticmethod
    def issue_token_pair(user: User) -> TokenPair:
        settings = get_settings()
        access = create_access_token(subject=user.id, role=user.role)
        refresh = create_refresh_token(subject=user.id, role=user.role)
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    def refresh_pair(db: Session, *, refresh_token: str) -> TokenPair:
        payload = decode_token(refresh_token, expected_type="refresh")
        user = db.get(User, int(payload.sub))
        if user is None or not user.is_active:
            raise InvalidCredentialsError("User no longer exists or is disabled")
        return AuthService.issue_token_pair(user)

    @staticmethod
    def register(db: Session, *, payload: UserCreate, requesting_role: Role | None) -> User:
        """Register a new user.

        When called by an admin (``requesting_role == Role.ADMIN``) the role
        on the payload is honored. Otherwise (self-signup, if enabled) the
        role is forced to VIEWER to prevent privilege escalation.
        """
        existing = crud.user.get_by_email(db=db, email=payload.email)
        if existing is not None:
            raise UserAlreadyExistsError(f"A user with email '{payload.email}' already exists")

        if requesting_role != Role.ADMIN:
            payload = payload.model_copy(update={"role": Role.VIEWER})

        return crud.user.create(db=db, obj_in=payload)


auth_service = AuthService()
