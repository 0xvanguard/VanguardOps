from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any
from datetime import datetime
from app.models.workflow import WorkflowStatus

class WorkflowBase(BaseModel):
    name: str = Field(..., description="Nombre del flujo de trabajo")
    trigger_type: str = Field(..., description="Evento que dispara el flujo (ej: ticket_created)")
    description: Optional[str] = None
    status: WorkflowStatus = Field(default=WorkflowStatus.PENDING)
    ticket_id: Optional[int] = None
    config_data: Optional[Dict[str, Any]] = None

class WorkflowCreate(WorkflowBase):
    pass

class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    trigger_type: Optional[str] = None
    description: Optional[str] = None
    status: Optional[WorkflowStatus] = None
    ticket_id: Optional[int] = None
    config_data: Optional[Dict[str, Any]] = None
    execution_logs: Optional[Dict[str, Any]] = None

class WorkflowRead(WorkflowBase):
    id: int
    execution_logs: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
