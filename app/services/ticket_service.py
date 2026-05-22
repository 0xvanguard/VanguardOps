from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.schemas.ticket import TicketCreate
from app.services.rules import calculate_priority, SLA_HOURS
from app.services.assignment_service import assignment_service
from app.services.workflow_service import workflow_service
from app import crud

class TicketService:
    @staticmethod
    def process_new_ticket(db: Session, ticket_in: TicketCreate):
        """
        Orquesta la creación de un ticket:
        1. Calcula prioridad final.
        2. Asigna SLA (due_at).
        3. Realiza asignación inicial si está vacía.
        4. Guarda en BD.
        5. Dispara workflows asociados al tipo de evento.
        """
        # Calcular Prioridad Real
        priority = calculate_priority(ticket_in.severity, ticket_in.category)
        ticket_in.priority = priority
        
        # Calcular SLA (due_at)
        sla_hours = SLA_HOURS.get(priority, 24)
        ticket_in.due_at = datetime.utcnow() + timedelta(hours=sla_hours)
        
        # Asignación Inicial de Grupo
        if not ticket_in.assigned_to:
            ticket_in.assigned_to = assignment_service.get_initial_assignment(ticket_in.category)
            
        # 1. Persistir ticket en DB
        db_ticket = crud.ticket.create(db=db, obj_in=ticket_in)
        
        # 2. Disparar Workflows si aplica la categoría
        workflow_service.trigger_workflow_for_ticket(db=db, ticket_id=db_ticket.id, category=ticket_in.category)
        
        return db_ticket

ticket_service = TicketService()
