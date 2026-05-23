"""HTTP middlewares: request-id correlation and access logging."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.core.logging import get_logger

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id and emit a structured access log per request.

    Every request is given an ``X-Request-ID`` (taken from the inbound header
    if present, otherwise generated). The id is bound to the structlog context
    so that any log emitted while handling the request is automatically
    correlated.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request_failed",
                duration_ms=round(duration_ms, 2),
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000

        # Skip access logs for health/metrics noise unless we're in DEBUG.
        path = request.url.path
        if path not in ("/livez", "/readyz", "/metrics"):
            logger.info(
                "request_completed",
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject conservative security headers into every response.

    These do not replace a proper reverse-proxy hardening (e.g. CSP from a
    CDN) but protect the API in environments where it is exposed directly.
    """

    DEFAULT_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for header, value in self.DEFAULT_HEADERS.items():
            response.headers.setdefault(header, value)
        return response
