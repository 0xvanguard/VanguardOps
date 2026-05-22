from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
from app.models.ticket import TicketStatus, TicketPriority, TicketSeverity

class TicketBase(BaseModel):
    title: str = Field(..., description="Título corto del incidente")
    description: str = Field(..., description="Descripción detallada del incidente")
    category: Optional[str] = None
    status: TicketStatus = Field(default=TicketStatus.OPEN)
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM)
    severity: TicketSeverity = Field(default=TicketSeverity.MEDIUM)
    reporter: Optional[str] = None
    assigned_to: Optional[str] = None
    asset_id: Optional[int] = None

class TicketCreate(TicketBase):
    pass

class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    severity: Optional[TicketSeverity] = None
    reporter: Optional[str] = None
    assigned_to: Optional[str] = None
    asset_id: Optional[int] = None

class TicketRead(TicketBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
