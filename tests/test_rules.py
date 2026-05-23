"""Pure-function tests for the business rules module."""

from __future__ import annotations

from app.models.ticket import TicketPriority, TicketSeverity
from app.services.rules import (
    SLA_HOURS,
    calculate_priority,
    initial_assignee,
    workflow_for_category,
)


def test_security_category_always_critical():
    assert calculate_priority(TicketSeverity.LOW, "security") == TicketPriority.CRITICAL
    assert calculate_priority(TicketSeverity.HIGH, "security") == TicketPriority.CRITICAL


def test_critical_severity_overrides_category():
    assert calculate_priority(TicketSeverity.CRITICAL, "password_reset") == TicketPriority.CRITICAL


def test_priority_mirrors_severity_otherwise():
    assert calculate_priority(TicketSeverity.HIGH, None) == TicketPriority.HIGH
    assert calculate_priority(TicketSeverity.MEDIUM, "access") == TicketPriority.MEDIUM
    assert calculate_priority(TicketSeverity.LOW, None) == TicketPriority.LOW


def test_sla_hours_complete_for_every_priority():
    for prio in TicketPriority:
        assert prio in SLA_HOURS, f"missing SLA mapping for {prio.value}"
    # Critical SLA must be the strictest.
    assert SLA_HOURS[TicketPriority.CRITICAL] < SLA_HOURS[TicketPriority.HIGH]


def test_initial_assignee_falls_back_to_default():
    assert initial_assignee("unknown") == "L1_Service_Desk"
    assert initial_assignee(None) == "L1_Service_Desk"
    assert initial_assignee("Network") == "L2_Network_Team"  # case-insensitive


def test_workflow_for_category_match_and_miss():
    assert workflow_for_category("password_reset") == "wf_auto_reset"
    assert workflow_for_category("security") is None
    assert workflow_for_category(None) is None
