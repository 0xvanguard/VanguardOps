"""Pure business rules for triage, routing and SLA computation.

Kept dependency-free so they can be unit-tested in isolation and reused
from both the API and the Celery worker without dragging in the ORM.
"""

from __future__ import annotations

from app.models.ticket import TicketPriority, TicketSeverity

# --- SLA -------------------------------------------------------------------

#: Hours of due time per priority. Tweak via configuration in a future
#: iteration if SLAs become customer-specific.
SLA_HOURS: dict[TicketPriority, int] = {
    TicketPriority.CRITICAL: 2,
    TicketPriority.HIGH: 4,
    TicketPriority.MEDIUM: 24,
    TicketPriority.LOW: 48,
}

# --- Routing ---------------------------------------------------------------

CATEGORY_ROUTING: dict[str, str] = {
    "network": "L2_Network_Team",
    "access": "L1_Service_Desk",
    "hardware": "L1_Field_Support",
    "security": "L3_Security_Ops",
    "password_reset": "L1_Service_Desk",
    "connectivity": "L2_Network_Team",
    "endpoint_health": "L1_Field_Support",
}
DEFAULT_ROUTING: str = "L1_Service_Desk"

# --- Workflow auto-trigger -------------------------------------------------

CATEGORY_WORKFLOWS: dict[str, str] = {
    "password_reset": "wf_auto_reset",
    "connectivity": "wf_ping_trace",
    "endpoint_health": "wf_system_diag",
    "network": "wf_ping_trace",
}


def calculate_priority(severity: TicketSeverity, category: str | None) -> TicketPriority:
    """Derive a ticket's priority from severity and category.

    The rule is intentionally simple and predictable: critical severity OR
    a security category always escalate to ``CRITICAL``; otherwise the
    priority mirrors the severity.
    """
    cat = (category or "").lower()
    if severity == TicketSeverity.CRITICAL or cat == "security":
        return TicketPriority.CRITICAL
    if severity == TicketSeverity.HIGH:
        return TicketPriority.HIGH
    if severity == TicketSeverity.MEDIUM:
        return TicketPriority.MEDIUM
    return TicketPriority.LOW


def initial_assignee(category: str | None) -> str:
    """Return the queue/team that should pick up a ticket of this category."""
    if not category:
        return DEFAULT_ROUTING
    return CATEGORY_ROUTING.get(category.lower(), DEFAULT_ROUTING)


def workflow_for_category(category: str | None) -> str | None:
    """Return the workflow to auto-trigger for a category, if any."""
    if not category:
        return None
    return CATEGORY_WORKFLOWS.get(category.lower())
