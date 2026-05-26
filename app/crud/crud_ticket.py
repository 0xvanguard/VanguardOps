from typing import List, Optional
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
from app.crud.base import CRUDBase
from app.models.ticket import Ticket, TicketStatus, TicketPriority, TicketSeverity
from app.schemas.ticket import TicketCreate, TicketUpdate

class CRUDTicket(CRUDBase[Ticket, TicketCreate, TicketUpdate]):
    def get_multi_with_filters(
        self, 
        db: Session, 
        *, 
        status: Optional[TicketStatus] = None,
        severity: Optional[TicketSeverity] = None,
        priority: Optional[TicketPriority] = None,
        asset_id: Optional[int] = None,
        skip: int = 0, 
        limit: int = 100
    ) -> List[Ticket]:
        query = db.query(self.model)
        
        if status is not None:
            query = query.filter(Ticket.status == status)
        if severity is not None:
            query = query.filter(Ticket.severity == severity)
        if priority is not None:
            query = query.filter(Ticket.priority == priority)
        if asset_id is not None:
            query = query.filter(Ticket.asset_id == asset_id)
            
        return query.offset(skip).limit(limit).all()

ticket = CRUDTicket(Ticket)
