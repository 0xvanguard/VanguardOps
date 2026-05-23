from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any
from datetime import datetime

class ActivityLogBase(BaseModel):
    event_type: str = Field(..., description="Tipo de evento (ej: ticket_created, workflow_triggered)")
    entity_type: str = Field(..., description="Entidad afectada (ej: ticket, workflow)")
    entity_id: int
    actor_type: str = Field(default="system")
    actor_id: Optional[str] = None
    details_json: Optional[Dict[str, Any]] = None

class ActivityLogCreate(ActivityLogBase):
    pass

class ActivityLogRead(ActivityLogBase):
    id: int
    timestamp_utc: datetime
    
    model_config = ConfigDict(from_attributes=True)
