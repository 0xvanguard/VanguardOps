"""Initial-routing service.

Currently a thin wrapper over :func:`app.services.rules.initial_assignee`,
but kept as a separate seam so future logic (e.g. team load balancing,
on-call schedules) can land here without changing callers.
"""

from __future__ import annotations

from app.services.rules import initial_assignee


class AssignmentService:
    @staticmethod
    def get_initial_assignment(category: str | None) -> str:
        return initial_assignee(category)


assignment_service = AssignmentService()
