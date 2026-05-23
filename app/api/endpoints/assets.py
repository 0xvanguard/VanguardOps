"""Asset endpoints (list, search, get, create, update)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app import crud
from app.api.deps import (
    DbSession,
    PaginationDep,
    require_operator,
    require_viewer,
)
from app.core.exceptions import AssetNotFoundError
from app.models.asset import AssetStatus
from app.schemas.asset import AssetCreate, AssetRead, AssetUpdate
from app.schemas.common import Page

router = APIRouter()


@router.post(
    "/",
    response_model=AssetRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator)],
    summary="Register a new asset",
)
def create_asset(asset_in: AssetCreate, db: DbSession) -> AssetRead:
    return crud.asset.create(db=db, obj_in=asset_in)  # type: ignore[return-value]


@router.get(
    "/",
    response_model=Page[AssetRead],
    dependencies=[Depends(require_viewer)],
    summary="List assets (paginated)",
)
def list_assets(db: DbSession, pagination: PaginationDep) -> Page[AssetRead]:
    items = crud.asset.get_multi(db=db, skip=pagination.offset, limit=pagination.limit)
    total = crud.asset.count(db=db)
    return Page[AssetRead].build(
        items=[AssetRead.model_validate(a) for a in items],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get(
    "/by-status/{status_value}",
    response_model=list[AssetRead],
    dependencies=[Depends(require_viewer)],
)
def list_assets_by_status(
    status_value: AssetStatus,
    db: DbSession,
    pagination: PaginationDep,
) -> list[AssetRead]:
    items = crud.asset.get_by_status(
        db=db, status=status_value, skip=pagination.offset, limit=pagination.limit
    )
    return [AssetRead.model_validate(a) for a in items]


@router.get(
    "/by-ip/{ip}",
    response_model=AssetRead,
    dependencies=[Depends(require_viewer)],
)
def get_asset_by_ip(ip: str, db: DbSession) -> AssetRead:
    asset = crud.asset.get_by_ip(db=db, ip_address=ip)
    if asset is None:
        raise AssetNotFoundError(f"No asset found with ip {ip}")
    return AssetRead.model_validate(asset)


@router.get(
    "/{asset_id}",
    response_model=AssetRead,
    dependencies=[Depends(require_viewer)],
)
def get_asset(asset_id: int, db: DbSession) -> AssetRead:
    asset = crud.asset.get(db=db, id=asset_id)
    if asset is None:
        raise AssetNotFoundError(f"Asset {asset_id} was not found")
    return AssetRead.model_validate(asset)


@router.patch(
    "/{asset_id}",
    response_model=AssetRead,
    dependencies=[Depends(require_operator)],
    summary="Update an asset",
)
def update_asset(
    asset_id: int,
    update_in: AssetUpdate,
    db: DbSession,
) -> AssetRead:
    asset = crud.asset.get(db=db, id=asset_id)
    if asset is None:
        raise AssetNotFoundError(f"Asset {asset_id} was not found")
    return crud.asset.update(db=db, db_obj=asset, obj_in=update_in)  # type: ignore[return-value]
