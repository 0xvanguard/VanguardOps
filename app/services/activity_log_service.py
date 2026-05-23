from sqlalchemy.orm import Session
from app import crud
from app.schemas.activity_log import ActivityLogCreate
from typing import Dict, Any, Optional

class ActivityLogService:
    @staticmethod
    def log_event(
        db: Session,
        event_type: str,
        entity_type: str,
        entity_id: int,
        actor_type: str = "system",
        actor_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Registra un evento de forma síncrona en el log de auditoría"""
        log_in = ActivityLogCreate(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_type=actor_type,
            actor_id=actor_id,
            details_json=details or {}
        )
        return crud.activity_log.create(db=db, obj_in=log_in)

activity_log_service = ActivityLogService()
