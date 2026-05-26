# pyrefly: ignore [missing-import]
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
from app.models.asset import AssetType, AssetStatus

class AssetBase(BaseModel):
    name: str = Field(..., description="Nombre identificador del activo")
    ip_address: Optional[str] = Field(None, description="Dirección IP (opcional)")
    asset_type: AssetType = Field(default=AssetType.OTHER)
    description: Optional[str] = None
    owner: Optional[str] = None
    location: Optional[str] = None
    status: AssetStatus = Field(default=AssetStatus.ACTIVE)

class AssetCreate(AssetBase):
    pass

class AssetUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    asset_type: Optional[AssetType] = None
    description: Optional[str] = None
    owner: Optional[str] = None
    location: Optional[str] = None
    status: Optional[AssetStatus] = None

class AssetRead(AssetBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
