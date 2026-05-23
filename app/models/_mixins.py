"""Shared SQLAlchemy mixins used by every model.

* :class:`TimestampMixin` adds tz-aware ``created_at`` and ``updated_at``
  columns populated server-side with ``func.now()`` so the values are
  consistent across the API process and Celery workers.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
