from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import crud
from app.schemas.workflow import WorkflowRead, WorkflowCreate, WorkflowUpdate
from app.models.workflow import WorkflowStatus
from app.api import deps
from app.core.security import get_admin_token

router = APIRouter()

@router.post("/", response_model=WorkflowRead, dependencies=[Depends(get_admin_token)])
def create_workflow(*, db: Session = Depends(deps.get_db), workflow_in: WorkflowCreate):
    return crud.workflow.create(db=db, obj_in=workflow_in)

@router.get("/", response_model=List[WorkflowRead])
def read_workflows(skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)):
    return crud.workflow.get_multi(db=db, skip=skip, limit=limit)

@router.get("/by-ticket/{ticket_id}", response_model=List[WorkflowRead])
def read_workflows_by_ticket(ticket_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)):
    return crud.workflow.get_by_ticket(db=db, ticket_id=ticket_id, skip=skip, limit=limit)

@router.get("/by-status/{status}", response_model=List[WorkflowRead])
def read_workflows_by_status(status: WorkflowStatus, skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)):
    return crud.workflow.get_by_status(db=db, status=status, skip=skip, limit=limit)

@router.get("/{workflow_id}", response_model=WorkflowRead)
def read_workflow(workflow_id: int, db: Session = Depends(deps.get_db)):
    workflow = crud.workflow.get(db=db, id=workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow
