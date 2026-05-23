"""FastAPI exception handlers that translate exceptions into RFC 7807 payloads.

All handlers respond with ``Content-Type: application/problem+json``.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import VanguardOpsError
from app.core.logging import get_logger

logger = get_logger(__name__)

PROBLEM_JSON = "application/problem+json"
PROBLEM_BASE_URI = "https://errors.vanguardops.dev"


def _problem_response(
    status_code: int,
    *,
    code: str,
    title: str,
    detail: str,
    request: Request,
    extras: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"{PROBLEM_BASE_URI}/{code}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
        "instance": str(request.url.path),
    }
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        body["request_id"] = request_id
    if extras:
        body.update(extras)
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type=PROBLEM_JSON,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach all exception handlers to the given FastAPI application."""

    @app.exception_handler(VanguardOpsError)
    async def _handle_domain_error(request: Request, exc: VanguardOpsError):
        logger.info(
            "domain_error",
            code=exc.code,
            status=exc.status_code,
            detail=exc.detail,
            path=request.url.path,
        )
        return _problem_response(
            exc.status_code,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            request=request,
            extras=exc.extras or None,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException):
        # Map a few common status codes into stable ``code`` values so clients
        # can branch on them.
        code_map = {
            400: ("bad_request", "Bad Request"),
            401: ("unauthorized", "Unauthorized"),
            403: ("forbidden", "Forbidden"),
            404: ("not_found", "Not Found"),
            405: ("method_not_allowed", "Method Not Allowed"),
            409: ("conflict", "Conflict"),
            429: ("rate_limited", "Too Many Requests"),
        }
        code, title = code_map.get(exc.status_code, ("http_error", "HTTP Error"))
        return _problem_response(
            exc.status_code,
            code=code,
            title=title,
            detail=str(exc.detail) if exc.detail else title,
            request=request,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError):
        # Sanitize errors to ensure JSON-serializable output (Pydantic returns
        # rich objects in ``ctx`` that may not be serializable).
        errors: list[dict[str, Any]] = []
        for err in exc.errors():
            errors.append(
                {
                    "loc": list(err.get("loc", [])),
                    "msg": err.get("msg", ""),
                    "type": err.get("type", "value_error"),
                }
            )
        return _problem_response(
            422,
            code="validation_error",
            title="Validation Error",
            detail="One or more fields failed validation",
            request=request,
            extras={"errors": errors},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception):
        logger.exception(
            "unhandled_exception",
            path=request.url.path,
            exc_type=type(exc).__name__,
        )
        return _problem_response(
            500,
            code="internal_error",
            title="Internal Server Error",
            detail="An unexpected error occurred. The incident has been logged.",
            request=request,
        )
