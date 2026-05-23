"""Ticket schemas (input + output)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.ticket import TicketPriority, TicketSeverity, TicketStatus


class TicketBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=4000)
    category: str | None = Field(default=None, max_length=64)
    severity: TicketSeverity = TicketSeverity.MEDIUM
    reporter: str | None = Field(default=None, max_length=255)
    asset_id: int | None = None


class TicketCreate(TicketBase):
    """Payload accepted by ``POST /tickets``.

    ``priority``, ``status``, ``assigned_to`` and ``due_at`` are *derived*
    server-side and intentionally omitted from this schema to avoid clients
    overriding the SLA / triage logic.
    """


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    category: str | None = Field(default=None, max_length=64)
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    severity: TicketSeverity | None = None
    reporter: str | None = Field(default=None, max_length=255)
    assigned_to: str | None = Field(default=None, max_length=255)
    due_at: datetime | None = None
    asset_id: int | None = None


class TicketRead(TicketBase):
    id: int
    status: TicketStatus
    priority: TicketPriority
    assigned_to: str | None
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
