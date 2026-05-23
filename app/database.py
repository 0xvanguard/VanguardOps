"""SQLAlchemy engine, session factory and declarative base.

Highlights:

* The :class:`Base` declarative class uses an explicit naming convention so
  Alembic auto-generates predictable, portable migration names for indexes,
  unique constraints, foreign keys and primary keys.
* The engine is lazily configured with sane pool defaults for PostgreSQL
  and special-cased for SQLite (in-memory tests use a shared connection).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

# Naming convention recommended by Alembic / SQLAlchemy docs:
# https://alembic.sqlalchemy.org/en/latest/naming.html
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Declarative base used by all ORM models."""

    metadata = metadata


def _build_engine() -> Engine:
    settings = get_settings()
    url = settings.DATABASE_URL
    kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}

    if url.startswith("sqlite"):
        # SQLite needs ``check_same_thread=False`` to be used across threads
        # (uvicorn workers, Celery, tests). For prod we use Postgres.
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_recycle"] = 1800  # recycle connections every 30 min

    return create_engine(url, **kwargs)


engine: Engine = _build_engine()
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)
