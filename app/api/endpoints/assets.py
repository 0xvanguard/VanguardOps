from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import crud
from app.schemas.asset import AssetRead, AssetCreate, AssetUpdate
from app.models.asset import AssetStatus
from app.api import deps
from app.core.security import get_admin_token

router = APIRouter()

@router.post("/", response_model=AssetRead, dependencies=[Depends(get_admin_token)])
def create_asset(*, db: Session = Depends(deps.get_db), asset_in: AssetCreate):
    return crud.asset.create(db=db, obj_in=asset_in)

@router.get("/", response_model=List[AssetRead])
def read_assets(skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)):
    return crud.asset.get_multi(db=db, skip=skip, limit=limit)

@router.get("/by-status/{status}", response_model=List[AssetRead])
def read_assets_by_status(status: AssetStatus, skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)):
    return crud.asset.get_by_status(db=db, status=status, skip=skip, limit=limit)

@router.get("/by-ip/{ip}", response_model=AssetRead)
def read_asset_by_ip(ip: str, db: Session = Depends(deps.get_db)):
    asset = crud.asset.get_by_ip(db=db, ip_address=ip)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset

@router.get("/{asset_id}", response_model=AssetRead)
def read_asset(asset_id: int, db: Session = Depends(deps.get_db)):
    asset = crud.asset.get(db=db, id=asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset
