"""Domain exceptions and RFC 7807 (``application/problem+json``) error model.

The API exposes errors using the schema described in
`RFC 7807 <https://www.rfc-editor.org/rfc/rfc7807>`_, which is the de-facto
standard for HTTP API error payloads. This gives clients:

* a stable ``type`` URI they can branch on,
* a human-readable ``title``,
* a ``status`` matching the HTTP status code,
* a ``detail`` describing the specific occurrence, and
* optional extension fields like ``code``, ``request_id`` and ``errors``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class VanguardOpsError(Exception):
    """Base class for all domain errors raised by application code.

    Sub-classes set sensible defaults; instances may override ``detail`` and
    ``extras`` to enrich the response payload.
    """

    status_code: int = 500
    code: str = "internal_error"
    title: str = "Internal Server Error"

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        extras: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail: str = detail or self.title
        if code is not None:
            self.code = code
        self.extras: dict[str, Any] = dict(extras or {})


# --- 400 family ---------------------------------------------------------


class ValidationError(VanguardOpsError):
    status_code = 422
    code = "validation_error"
    title = "Validation Error"


class BadRequestError(VanguardOpsError):
    status_code = 400
    code = "bad_request"
    title = "Bad Request"


class UnauthorizedError(VanguardOpsError):
    status_code = 401
    code = "unauthorized"
    title = "Unauthorized"


class ForbiddenError(VanguardOpsError):
    status_code = 403
    code = "forbidden"
    title = "Forbidden"


class NotFoundError(VanguardOpsError):
    status_code = 404
    code = "not_found"
    title = "Not Found"


class ConflictError(VanguardOpsError):
    status_code = 409
    code = "conflict"
    title = "Conflict"


class IPBannedError(VanguardOpsError):
    status_code = 429
    code = "ip_banned"
    title = "IP Address Banned"


class RateLimitError(VanguardOpsError):
    status_code = 429
    code = "rate_limited"
    title = "Too Many Requests"


# --- Domain-specific (subclasses for documentation & branching) ---------


class InvalidStateTransitionError(ConflictError):
    """A state machine transition was rejected (e.g. CLOSED -> OPEN)."""

    code = "invalid_state_transition"
    title = "Invalid State Transition"


class AssetNotFoundError(NotFoundError):
    code = "asset_not_found"
    title = "Asset Not Found"


class TicketNotFoundError(NotFoundError):
    code = "ticket_not_found"
    title = "Ticket Not Found"


class WorkflowNotFoundError(NotFoundError):
    code = "workflow_not_found"
    title = "Workflow Not Found"


class UserAlreadyExistsError(ConflictError):
    code = "user_already_exists"
    title = "User Already Exists"


class InvalidCredentialsError(UnauthorizedError):
    code = "invalid_credentials"
    title = "Invalid Credentials"
