from sqlalchemy.orm import Session
from app.crud.base import CRUDBase
from app.models.asset import Asset, AssetStatus
from app.schemas.asset import AssetCreate, AssetUpdate
from typing import List, Optional

class CRUDAsset(CRUDBase[Asset, AssetCreate, AssetUpdate]):
    def get_by_status(self, db: Session, *, status: AssetStatus, skip: int = 0, limit: int = 100) -> List[Asset]:
        return db.query(self.model).filter(Asset.status == status).offset(skip).limit(limit).all()
        
    def get_by_ip(self, db: Session, *, ip_address: str) -> Optional[Asset]:
        return db.query(self.model).filter(Asset.ip_address == ip_address).first()

asset = CRUDAsset(Asset)
