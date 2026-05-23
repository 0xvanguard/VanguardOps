"""Idempotent startup hook: create the bootstrap admin user.

Schema management is intentionally **not** part of this module. Production
runs ``alembic upgrade head`` as a separate deployment step (see
``docker-compose.yml``); tests build the schema directly in
``tests/conftest.py`` to avoid coupling the test suite to Alembic.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import crud
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import Role
from app.database import SessionLocal
from app.schemas.auth import UserCreate

logger = get_logger(__name__)


def bootstrap_admin(db: Session | None = None) -> None:
    """Create the bootstrap admin user the first time the app boots.

    Safe to call on every startup: returns immediately once at least one
    user already exists. Wrapped in a context manager so the session is
    closed even if the create call raises (e.g. duplicate email under a
    parallel start).
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
