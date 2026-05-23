from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app import crud
from app.api import deps
from app.schemas.activity_log import ActivityLogRead

router = APIRouter()

@router.get("/", response_model=List[ActivityLogRead])
def read_logs(skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)):
    return crud.activity_log.get_multi(db=db, skip=skip, limit=limit)

@router.get("/{entity_type}/{entity_id}", response_model=List[ActivityLogRead])
def read_logs_by_entity(
    entity_type: str, entity_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)
):
    return crud.activity_log.get_by_entity(db=db, entity_type=entity_type, entity_id=entity_id, skip=skip, limit=limit)
