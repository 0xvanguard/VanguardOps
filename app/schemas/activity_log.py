"""Activity-log schemas (write-only by services, read-only via API)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActivityLogBase(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=64)
    entity_type: str = Field(..., min_length=1, max_length=32)
    entity_id: int
    actor_type: str = Field(default="system", max_length=32)
    actor_id: str | None = Field(default=None, max_length=64)
    details_json: dict[str, Any] | None = None


class ActivityLogCreate(ActivityLogBase):
    pass


class ActivityLogRead(ActivityLogBase):
    id: int
    timestamp_utc: datetime

    model_config = ConfigDict(from_attributes=True)
