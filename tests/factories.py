"""factory-boy factories for ORM models.

Each factory is bound at runtime to the per-test session via
:func:`register_session`. Tests never need to pass a session explicitly;
calling ``UserFactory()`` Just Works.
"""

from __future__ import annotations

import factory
from factory.alchemy import SQLAlchemyModelFactory
from sqlalchemy.orm import Session

from app.core.security import Role, hash_password
from app.models.asset import Asset, AssetStatus, AssetType
from app.models.ticket import (
    Ticket,
    TicketPriority,
    TicketSeverity,
    TicketStatus,
)
from app.models.user import User
from app.models.workflow import Workflow, WorkflowStatus

_SESSION: Session | None = None


def register_session(session: Session) -> None:
    """Bind every factory to ``session`` for the lifetime of a test."""
    global _SESSION
    _SESSION = session
    for factory_cls in (UserFactory, AssetFactory, TicketFactory, WorkflowFactory):
        factory_cls._meta.sqlalchemy_session = session  # type: ignore[attr-defined]


class _BaseFactory(SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session_persistence = "commit"


class UserFactory(_BaseFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@vanguardops.io")
    full_name = factory.Faker("name")
    hashed_password = factory.LazyFunction(lambda: hash_password("Test!2345"))
    role = Role.OPERATOR
    is_active = True


class AssetFactory(_BaseFactory):
    class Meta:
        model = Asset

    name = factory.Sequence(lambda n: f"asset-{n}")
    asset_type = AssetType.SERVER
    status = AssetStatus.ACTIVE
    ip_address = factory.Sequence(lambda n: f"10.0.{(n // 256) % 256}.{n % 256}")
    description = "Created by tests"
    owner = "QA"
    location = "datacenter-1"


class TicketFactory(_BaseFactory):
    class Meta:
        model = Ticket

    title = factory.Sequence(lambda n: f"ticket-{n}")
    description = "Synthetic ticket created by the test factory"
    category = "access"
    status = TicketStatus.OPEN
    priority = TicketPriority.MEDIUM
    severity = TicketSeverity.MEDIUM
    reporter = "tests@vanguardops.local"
    assigned_to = "L1_Service_Desk"


class WorkflowFactory(_BaseFactory):
    class Meta:
        model = Workflow

    name = "wf_auto_reset"
    trigger_type = "manual"
    description = "Synthetic workflow"
    status = WorkflowStatus.PENDING
    config_data = factory.LazyFunction(dict)
