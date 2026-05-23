"""ORM model registry.

Importing every model here ensures :data:`app.database.Base.metadata` knows
about all tables before Alembic autogenerates migrations.
"""

from app.models.activity_log import ActivityLog  # noqa: F401
from app.models.asset import Asset, AssetStatus, AssetType  # noqa: F401
from app.models.ticket import (  # noqa: F401
    Ticket,
    TicketPriority,
    TicketSeverity,
    TicketStatus,
)
from app.models.user import User  # noqa: F401
from app.models.workflow import Workflow, WorkflowStatus  # noqa: F401
