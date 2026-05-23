"""Reusable schema primitives (pagination, problem details, generics)."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

ItemT = TypeVar("ItemT")


class Page[ItemT](BaseModel):
    """Standard paginated response envelope.

    Mirrors what most enterprise APIs expose so consumers can build generic
    clients (e.g. ``while page.has_next``).
    """

    model_config = ConfigDict(from_attributes=True)

    items: list[ItemT]
    total: int = Field(..., ge=0, description="Total number of items matching the query")
    page: int = Field(..., ge=1, description="1-based page number")
    size: int = Field(..., ge=1, le=200, description="Items per page")
    has_next: bool = Field(..., description="True if a subsequent page exists")
    has_prev: bool = Field(..., description="True if a prior page exists")

    @classmethod
    def build(
        cls,
        *,
        items: list[ItemT],
        total: int,
        page: int,
        size: int,
    ) -> Page[ItemT]:
        return cls(
            items=items,
            total=total,
            page=page,
            size=size,
            has_next=(page * size) < total,
            has_prev=page > 1,
        )


class HealthStatus(BaseModel):
    status: str = Field(..., examples=["ok", "degraded"])
    service: str
    version: str


class ReadinessStatus(BaseModel):
    status: str = Field(..., examples=["ready", "not_ready"])
    checks: dict[str, str]


class ProblemDetails(BaseModel):
    """Schema documenting RFC 7807 error responses in OpenAPI."""

    type: str = Field(..., examples=["https://errors.vanguardops.dev/not_found"])
    title: str = Field(..., examples=["Not Found"])
    status: int = Field(..., examples=[404])
    detail: str = Field(..., examples=["Ticket 42 was not found"])
    code: str = Field(..., examples=["ticket_not_found"])
    instance: str = Field(..., examples=["/api/v1/tickets/42"])
    request_id: str | None = None
