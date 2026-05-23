from sqlalchemy import Column, Integer, String, DateTime, JSON
from datetime import datetime
from app.database import Base

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp_utc = Column(DateTime, default=datetime.utcnow, index=True)
    event_type = Column(String, index=True)
    entity_type = Column(String, index=True)
    entity_id = Column(Integer, index=True)
    actor_type = Column(String, default="system")
    actor_id = Column(String, nullable=True)
    details_json = Column(JSON, nullable=True)
