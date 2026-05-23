"""Activity-log CRUD operations (insert-only + filtered reads)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.activity_log import ActivityLog
from app.schemas.activity_log import ActivityLogCreate


class CRUDActivityLog(CRUDBase[ActivityLog, ActivityLogCreate, ActivityLogCreate]):
    def get_by_entity(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ActivityLog]:
        stmt = (
            select(ActivityLog)
            .where(
                ActivityLog.entity_type == entity_type,
                ActivityLog.entity_id == entity_id,
            )
            .order_by(ActivityLog.timestamp_utc.desc())
            .offset(skip)
            .limit(limit)
        )
        return db.execute(stmt).scalars().all()

    def get_multi_ordered(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> Sequence[ActivityLog]:
        stmt = (
            select(ActivityLog).order_by(ActivityLog.timestamp_utc.desc()).offset(skip).limit(limit)
        )
        return db.execute(stmt).scalars().all()

    def count_by_entity(self, db: Session, *, entity_type: str, entity_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(ActivityLog)
            .where(
                ActivityLog.entity_type == entity_type,
                ActivityLog.entity_id == entity_id,
            )
        )
        return int(db.execute(stmt).scalar_one())


activity_log = CRUDActivityLog(ActivityLog)
