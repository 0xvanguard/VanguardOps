"""Public CRUD facade.

Each domain entity is exposed as a singleton repository so application code
can write ``crud.ticket.get(...)`` without instantiating anything.
"""

from app.crud.crud_activity_log import activity_log  # noqa: F401
from app.crud.crud_asset import asset  # noqa: F401
from app.crud.crud_ticket import ticket  # noqa: F401
from app.crud.crud_user import user  # noqa: F401
from app.crud.crud_workflow import workflow  # noqa: F401
