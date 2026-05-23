"""Workflow execution record (one row per dispatched async run)."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models._mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.ticket import Ticket


class WorkflowStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


# Terminal states that should never transition again.
TERMINAL_WORKFLOW_STATUSES: set[WorkflowStatus] = {
    WorkflowStatus.SUCCESS,
    WorkflowStatus.FAILED,
    WorkflowStatus.CANCELLED,
}


class Workflow(Base, TimestampMixin):
    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        SAEnum(WorkflowStatus, name="workflow_status"),
        nullable=False,
        default=WorkflowStatus.PENDING,
    )

    ticket_id: Mapped[int | None] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True
    )
    ticket: Mapped[Ticket | None] = relationship(back_populates="workflows")

    # Free-form JSON for inputs / results; schema is per-workflow-name.
    config_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    execution_logs: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
