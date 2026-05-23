"""Thin facade for emitting audit-log events.

Keeping this in a service (instead of inlining ``crud.activity_log.create``
at every call site) gives us a single seam to:

* enrich every event with the current actor (set later by middleware), and
* swap the storage backend (e.g. emit to Kafka) without touching callers.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app import crud
from app.schemas.activity_log import ActivityLogCreate


class ActivityLogService:
    @staticmethod
    def log_event(
        db: Session,
        *,
        event_type: str,
        entity_type: str,
        entity_id: int,
        actor_type: str = "system",
        actor_id: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        log_in = ActivityLogCreate(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_type=actor_type,
            actor_id=actor_id,
            details_json=details or {},
        )
        return crud.activity_log.create(db=db, obj_in=log_in)


activity_log_service = ActivityLogService()
