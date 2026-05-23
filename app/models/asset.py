"""Infrastructure asset model (servers, workstations, network gear, apps)."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models._mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.ticket import Ticket


class AssetType(enum.StrEnum):
    SERVER = "SERVER"
    WORKSTATION = "WORKSTATION"
    NETWORK_DEVICE = "NETWORK_DEVICE"
    APPLICATION = "APPLICATION"
    OTHER = "OTHER"


class AssetStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MAINTENANCE = "MAINTENANCE"
    RETIRED = "RETIRED"


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), index=True, nullable=True)
    asset_type: Mapped[AssetType] = mapped_column(
        SAEnum(AssetType, name="asset_type"),
        nullable=False,
        default=AssetType.OTHER,
    )
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[AssetStatus] = mapped_column(
        SAEnum(AssetStatus, name="asset_status"),
        nullable=False,
        default=AssetStatus.ACTIVE,
    )

    tickets: Mapped[list[Ticket]] = relationship(
        back_populates="asset", cascade="save-update, merge"
    )
