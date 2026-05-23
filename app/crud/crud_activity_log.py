from typing import List
from sqlalchemy.orm import Session
from app.crud.base import CRUDBase
from app.models.activity_log import ActivityLog
from app.schemas.activity_log import ActivityLogCreate

class CRUDActivityLog(CRUDBase[ActivityLog, ActivityLogCreate, ActivityLogCreate]):
    def get_by_entity(
        self, db: Session, *, entity_type: str, entity_id: int, skip: int = 0, limit: int = 100
    ) -> List[ActivityLog]:
        return (
            db.query(self.model)
            .filter(ActivityLog.entity_type == entity_type, ActivityLog.entity_id == entity_id)
            .order_by(ActivityLog.timestamp_utc.desc())
            .offset(skip).limit(limit).all()
        )

activity_log = CRUDActivityLog(ActivityLog)
