"""Startup hooks: bootstrap admin user, ensure DB schema in dev/test.

Production deployments use Alembic migrations; the ``ensure_schema`` helper
is only used for the test database so we don't need to run Alembic from
``conftest.py``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import crud
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import Role
from app.database import Base, SessionLocal, engine
from app.schemas.auth import UserCreate

logger = get_logger(__name__)


def ensure_schema() -> None:
    """Create tables if they don't exist. Used in dev/test only."""
    Base.metadata.create_all(bind=engine)


def bootstrap_admin(db: Session | None = None) -> None:
    """Idempotently create the bootstrap admin user when no users exist.

    Safe to call on every startup: does nothing once users are present.
    """
    settings = get_settings()
    own_session = db is None
    db = db or SessionLocal()
    try:
        if crud.user.count(db=db) > 0:
            return
        admin = UserCreate(
            email=settings.BOOTSTRAP_ADMIN_EMAIL,
            password=settings.BOOTSTRAP_ADMIN_PASSWORD,
            full_name="VanguardOps Admin",
            role=Role.ADMIN,
            is_active=True,
        )
        crud.user.create(db=db, obj_in=admin)
        logger.info(
            "bootstrap_admin_created",
            email=settings.BOOTSTRAP_ADMIN_EMAIL,
        )
    finally:
        if own_session:
            db.close()
