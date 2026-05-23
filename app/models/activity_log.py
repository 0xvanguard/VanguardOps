"""Append-only audit log of every meaningful domain event."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ActivityLog(Base):
    """Immutable record of a single domain event.

    Rows are never updated or deleted (``UPDATE``/``DELETE`` are not exposed
    by the API). The composite index on ``(entity_type, entity_id)`` makes
    the most common query - "give me the timeline for ticket X" - fast.
    """

    __tablename__ = "activity_logs"
    __table_args__ = (Index("ix_activity_logs_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    timestamp_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    entity_id: Mapped[int] = mapped_column(index=True, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), default="system", nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
