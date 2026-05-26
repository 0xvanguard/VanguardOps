# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
from app.workers.celery_app import celery_app
from app.database import SessionLocal
from app import crud
from app.models.workflow import WorkflowStatus
from app.workers.workflow_executor import WorkflowExecutor
from app.services.activity_log_service import activity_log_service

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def execute_workflow_task(self, workflow_id: int):
    db: Session = SessionLocal()
    try:
        workflow = crud.workflow.get(db=db, id=workflow_id)
        if not workflow:
            return {"error": "Workflow no encontrado"}

        # Prevención estricta de duplicados e idempotencia
        if workflow.status not in [WorkflowStatus.PENDING, WorkflowStatus.RETRYING]:
            activity_log_service.log_event(
                db=db, event_type="workflow_skipped_duplicate", entity_type="workflow", entity_id=workflow_id,
                details={"current_status": workflow.status, "msg": "Intento de ejecución descartado por estado."}
            )
            return {"error": "Skipped due to status"}

        # Marcar como RUNNING
        workflow.status = WorkflowStatus.RUNNING
        db.commit()
        
        activity_log_service.log_event(
            db=db, event_type="workflow_started", entity_type="workflow", entity_id=workflow_id,
            details={"worker_task_id": self.request.id}
        )
        
        # Ejecutar Lógica Real Desacoplada
        try:
            result = WorkflowExecutor.run_workflow(workflow.name, workflow.config_data or {})
            
            # Marcar SUCCESS
            workflow.status = WorkflowStatus.SUCCESS
            workflow.execution_logs = result
            db.commit()
            
            activity_log_service.log_event(
                db=db, event_type="workflow_succeeded", entity_type="workflow", entity_id=workflow_id,
                details={"result": result}
            )
            return result
            
        except Exception as exec_error:
            # Forzar re-levantamiento para Retry
            raise exec_error

    except Exception as exc:
        db.rollback()
        # Refrescar instancia para actualizar estado sin conflictos de sesión
        workflow = crud.workflow.get(db=db, id=workflow_id)
        if workflow:
            if self.request.retries < self.max_retries:
                workflow.status = WorkflowStatus.RETRYING
                db.commit()
                activity_log_service.log_event(
                    db=db, event_type="workflow_retry_scheduled", entity_type="workflow", entity_id=workflow_id,
                    details={"error": str(exc), "retry_count": self.request.retries + 1}
                )
                raise self.retry(exc=exc)
            else:
                workflow.status = WorkflowStatus.FAILED
                workflow.execution_logs = {"error": str(exc), "final_failure": True}
                db.commit()
                activity_log_service.log_event(
                    db=db, event_type="workflow_failed", entity_type="workflow", entity_id=workflow_id,
                    details={"error": str(exc)}
                )
        return {"error": str(exc)}
    finally:
        db.close()
