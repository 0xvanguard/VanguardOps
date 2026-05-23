"""Workflow schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.workflow import WorkflowStatus


class WorkflowBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    trigger_type: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=1000)
    ticket_id: int | None = None
    config_data: dict[str, Any] | None = None


class WorkflowCreate(WorkflowBase):
    """``status`` is forced to PENDING server-side; not accepted from clients."""


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    trigger_type: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=1000)
    status: WorkflowStatus | None = None
    ticket_id: int | None = None
    config_data: dict[str, Any] | None = None
    execution_logs: dict[str, Any] | None = None


class WorkflowRead(WorkflowBase):
    id: int
    status: WorkflowStatus
    execution_logs: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
