"""Asset CRUD operations."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.asset import Asset, AssetStatus
from app.schemas.asset import AssetCreate, AssetUpdate


class CRUDAsset(CRUDBase[Asset, AssetCreate, AssetUpdate]):
    def get_by_status(
        self, db: Session, *, status: AssetStatus, skip: int = 0, limit: int = 100
    ) -> Sequence[Asset]:
        stmt = select(Asset).where(Asset.status == status).offset(skip).limit(limit)
        return db.execute(stmt).scalars().all()

    def get_by_ip(self, db: Session, *, ip_address: str) -> Asset | None:
        stmt = select(Asset).where(Asset.ip_address == ip_address)
        return db.execute(stmt).scalar_one_or_none()


asset = CRUDAsset(Asset)
