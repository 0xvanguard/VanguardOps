from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app import crud
from app.schemas.ticket import TicketRead, TicketCreate, TicketUpdate
from app.models.ticket import TicketStatus, TicketPriority, TicketSeverity
from app.api import deps
from app.core.security import get_admin_token
from app.services.ticket_service import ticket_service
from app.services.activity_log_service import activity_log_service

router = APIRouter()

@router.post("/", response_model=TicketRead, dependencies=[Depends(get_admin_token)])
def create_ticket(*, db: Session = Depends(deps.get_db), ticket_in: TicketCreate):
    return ticket_service.process_new_ticket(db=db, ticket_in=ticket_in)

@router.get("/", response_model=List[TicketRead])
def read_tickets(skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)):
    return crud.ticket.get_multi(db=db, skip=skip, limit=limit)

@router.get("/filter", response_model=List[TicketRead])
def filter_tickets(
    status: Optional[TicketStatus] = None,
    severity: Optional[TicketSeverity] = None,
    priority: Optional[TicketPriority] = None,
    asset_id: Optional[int] = None,
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(deps.get_db)
):
    return crud.ticket.get_multi_with_filters(
        db=db, status=status, severity=severity, priority=priority, asset_id=asset_id, skip=skip, limit=limit
    )

@router.get("/{ticket_id}", response_model=TicketRead)
def read_ticket(ticket_id: int, db: Session = Depends(deps.get_db)):
    ticket = crud.ticket.get(db=db, id=ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket

@router.put("/{ticket_id}", response_model=TicketRead, dependencies=[Depends(get_admin_token)])
def update_ticket(ticket_id: int, ticket_in: TicketUpdate, db: Session = Depends(deps.get_db)):
    ticket = crud.ticket.get(db=db, id=ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    updated_ticket = crud.ticket.update(db=db, db_obj=ticket, obj_in=ticket_in)
    
    activity_log_service.log_event(
        db=db, event_type="ticket_updated", entity_type="ticket", entity_id=ticket_id,
        details={"updated_fields": ticket_in.model_dump(exclude_unset=True)}
    )
    
    return updated_ticket
