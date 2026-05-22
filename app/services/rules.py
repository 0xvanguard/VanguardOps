from datetime import timedelta
from app.models.ticket import TicketPriority, TicketSeverity

# Mapeo de SLA (horas) por Prioridad
SLA_HOURS = {
    TicketPriority.CRITICAL: 2,
    TicketPriority.HIGH: 4,
    TicketPriority.MEDIUM: 24,
    TicketPriority.LOW: 48
}

# Reglas de asignación inicial por categoría
CATEGORY_ROUTING = {
    "network": "L2_Network_Team",
    "access": "L1_Service_Desk",
    "hardware": "L1_Field_Support",
    "security": "L3_Security_Ops",
    "password_reset": "L1_Service_Desk"
}
DEFAULT_ROUTING = "L1_Service_Desk"

# Flujos a disparar según categoría
CATEGORY_WORKFLOWS = {
    "password_reset": "wf_auto_reset",
    "connectivity": "wf_ping_trace",
    "endpoint_health": "wf_system_diag",
    "network": "wf_ping_trace"
}

def calculate_priority(severity: TicketSeverity, category: str) -> TicketPriority:
    """Calcula la prioridad basada en severidad y categoría"""
    if not category:
        category = ""
        
    if severity == TicketSeverity.CRITICAL or category.lower() == "security":
        return TicketPriority.CRITICAL
    if severity == TicketSeverity.HIGH:
        return TicketPriority.HIGH
    if severity == TicketSeverity.MEDIUM:
        return TicketPriority.MEDIUM
    return TicketPriority.LOW
