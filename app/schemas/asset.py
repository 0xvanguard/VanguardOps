"""Asset schemas (input + output)."""

from __future__ import annotations

import ipaddress
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.asset import AssetStatus, AssetType


def _validate_ip(v: str | None) -> str | None:
    """Reject anything that is not a valid IPv4/IPv6 literal.

    Empty strings are normalised to ``None`` so the column stays NULL instead
    of holding ``""``.
    """
    if v is None or v == "":
        return None
    try:
        ipaddress.ip_address(v)
    except ValueError as exc:
        raise ValueError(f"'{v}' is not a valid IPv4/IPv6 address") from exc
    return v


class AssetBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Display name")
    ip_address: str | None = Field(default=None, max_length=45, description="IPv4/IPv6 address")
    asset_type: AssetType = AssetType.OTHER
    description: str | None = Field(default=None, max_length=1000)
    owner: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    status: AssetStatus = AssetStatus.ACTIVE

    @field_validator("ip_address")
    @classmethod
    def _check_ip(cls, v: str | None) -> str | None:
        return _validate_ip(v)


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    ip_address: str | None = Field(default=None, max_length=45)
    asset_type: AssetType | None = None
    description: str | None = Field(default=None, max_length=1000)
    owner: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    status: AssetStatus | None = None

    @field_validator("ip_address")
    @classmethod
    def _check_ip(cls, v: str | None) -> str | None:
        return _validate_ip(v)


class AssetRead(AssetBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
