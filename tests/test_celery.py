from unittest.mock import patch
from app.models.workflow import WorkflowStatus
from app.workers.tasks import execute_workflow_task
from app.workers.workflow_executor import WorkflowExecutor
from app import crud

def test_workflow_execution_success(db_engine, client, admin_headers):
    # 1. Crear workflow pendiente vía API o simulación
    res = client.post("/api/v1/workflows/", json={"name": "wf_auto_reset", "trigger_type": "manual"}, headers=admin_headers)
    assert res.status_code == 200
    wf_id = res.json()["id"]

    # 2. Ejecutar la tarea de Celery sincrónicamente para probar la lógica
    # Usamos execute_workflow_task llamándola directamente como función normal
    result = execute_workflow_task(workflow_id=wf_id)
    
    # 3. Validar estado cambiado a SUCCESS y result
    assert result.get("status") == "success"
    
    wf_updated = client.get(f"/api/v1/workflows/{wf_id}").json()
    assert wf_updated["status"] == "SUCCESS"
    assert wf_updated["execution_logs"]["action"] == "password_reset"
    
    # 4. Validar auditoría
    logs_res = client.get(f"/api/v1/activity-log/workflow/{wf_id}")
    logs = logs_res.json()
    event_types = [log["event_type"] for log in logs]
    assert "workflow_started" in event_types
    assert "workflow_succeeded" in event_types

def test_workflow_anti_duplication(db_engine, client, admin_headers):
    res = client.post("/api/v1/workflows/", json={"name": "wf_connectivity_triage", "trigger_type": "manual"}, headers=admin_headers)
    wf_id = res.json()["id"]

    # Ejecutar una vez
    execute_workflow_task(workflow_id=wf_id)
    
    # Intentar ejecutar nuevamente
    result = execute_workflow_task(workflow_id=wf_id)
    
    # Debe saltar por estado no válido (ya es SUCCESS)
    assert result.get("error") == "Skipped due to status"
    
    logs_res = client.get(f"/api/v1/activity-log/workflow/{wf_id}")
    event_types = [log["event_type"] for log in logs_res.json()]
    assert "workflow_skipped_duplicate" in event_types
