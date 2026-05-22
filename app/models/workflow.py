from sqlalchemy import Column, Integer, String, DateTime, Enum, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base

class WorkflowStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    trigger_type = Column(String, index=True)
    description = Column(String, nullable=True)
    status = Column(Enum(WorkflowStatus), default=WorkflowStatus.PENDING)
    
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=True)
    
    # Store dynamic workflow definition or execution result data
    config_data = Column(JSON, nullable=True)
    execution_logs = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    ticket = relationship("Ticket", backref="workflows")
