from typing import List, Optional
from sqlalchemy.orm import Session
from app.crud.base import CRUDBase
from app.models.workflow import Workflow, WorkflowStatus
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate

class CRUDWorkflow(CRUDBase[Workflow, WorkflowCreate, WorkflowUpdate]):
    def get_by_ticket(
        self, db: Session, *, ticket_id: int, skip: int = 0, limit: int = 100
    ) -> List[Workflow]:
        return db.query(self.model).filter(Workflow.ticket_id == ticket_id).offset(skip).limit(limit).all()
        
    def get_by_status(
        self, db: Session, *, status: WorkflowStatus, skip: int = 0, limit: int = 100
    ) -> List[Workflow]:
        return db.query(self.model).filter(Workflow.status == status).offset(skip).limit(limit).all()
        
    def get_by_ticket_and_status(
        self, db: Session, *, ticket_id: int, status: WorkflowStatus
    ) -> List[Workflow]:
        return (
            db.query(self.model)
            .filter(Workflow.ticket_id == ticket_id, Workflow.status == status)
            .all()
        )

workflow = CRUDWorkflow(Workflow)
