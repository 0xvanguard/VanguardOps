# pyrefly: ignore [missing-import]
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
        db_workflow = crud.workflow.create(db=db, obj_in=workflow_in)
        
        from app.services.activity_log_service import activity_log_service
        activity_log_service.log_event(
            db=db, event_type="workflow_triggered", entity_type="ticket", entity_id=ticket_id,
            details={"workflow_id": db_workflow.id, "workflow_name": workflow_name}
        )
        
        # Encolar ejecución asíncrona real en Celery
        from app.workers.tasks import execute_workflow_task
        task = execute_workflow_task.delay(db_workflow.id)
        
        # Log del encolamiento
        activity_log_service.log_event(
            db=db, event_type="workflow_enqueued", entity_type="workflow", entity_id=db_workflow.id,
            details={"celery_task_id": task.id}
        )
        
        return db_workflow

workflow_service = WorkflowService()
