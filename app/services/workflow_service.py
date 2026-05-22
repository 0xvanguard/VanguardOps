from sqlalchemy.orm import Session
from app import crud
from app.schemas.workflow import WorkflowCreate
from app.models.workflow import WorkflowStatus
from app.services.rules import CATEGORY_WORKFLOWS

class WorkflowService:
    @staticmethod
    def trigger_workflow_for_ticket(db: Session, ticket_id: int, category: str):
        """Dispara un workflow asíncrono si la categoría del ticket lo amerita"""
        if not category:
            return None
            
        workflow_name = CATEGORY_WORKFLOWS.get(category.lower())
        if not workflow_name:
            return None
            
        # Crear registro de workflow pendiente
        workflow_in = WorkflowCreate(
            name=workflow_name,
            trigger_type="ticket_created",
            description=f"Auto-triggered for ticket {ticket_id}",
            status=WorkflowStatus.PENDING,
            ticket_id=ticket_id,
            config_data={"target_category": category}
        )
        return crud.workflow.create(db=db, obj_in=workflow_in)

workflow_service = WorkflowService()
