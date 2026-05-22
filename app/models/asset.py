from sqlalchemy import Column, Integer, String, DateTime, Enum
from sqlalchemy.orm import relationship
import enum
from datetime import datetime
from app.database import Base

class AssetType(str, enum.Enum):
    SERVER = "SERVER"
    WORKSTATION = "WORKSTATION"
    NETWORK_DEVICE = "NETWORK_DEVICE"
    APPLICATION = "APPLICATION"
    OTHER = "OTHER"

class AssetStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MAINTENANCE = "MAINTENANCE"
    RETIRED = "RETIRED"

class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    ip_address = Column(String, index=True, nullable=True)
    asset_type = Column(Enum(AssetType), default=AssetType.OTHER)
    description = Column(String, nullable=True)
    
    owner = Column(String, nullable=True)
    location = Column(String, nullable=True)
    status = Column(Enum(AssetStatus), default=AssetStatus.ACTIVE)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tickets = relationship("Ticket", back_populates="asset")
