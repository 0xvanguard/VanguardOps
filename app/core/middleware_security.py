"""HTTP middleware: dynamic IP ban check + sliding-window rate limiter.

Decision flow per request
-------------------------
1. Health and metrics endpoints are exempt (``EXEMPT_PATH_PREFIXES``).
2. Resolve the client IP (honouring ``X-Forwarded-For`` only when
   ``TRUST_PROXY=True``).
3. CIDR whitelist short-circuit.
4. ``IPBanlist.is_banned(ip)`` → 429 ``ip_banned`` if active.
5. Pick the rate-limit rule for the path.
6. ``SlidingWindowRateLimiter.check(...)`` → 429 ``rate_limited`` if full.
7. Forward to the application via ``call_next``. Modern Starlette routes
   exception responses (4xx/5xx from raised :class:`VanguardOpsError`)
   back through ``call_next``'s return value, so the after-call hook
   below sees the actual status code regardless of whether the route
   returned a :class:`Response` or raised.
8. After-call hook:
   * inject ``X-RateLimit-*`` headers,
   * record ``track_auth_failure`` on 401 when the path is an auth one,
   * record ``track_scan`` on 404.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import ClassVar

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.ip_banlist import get_banlist
from app.services.rate_limiter import RateLimitResult, get_rate_limiter

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Rate-limit rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateRule:
    pattern: re.Pattern[str]
    scope: str
    limit_setting: str  # name of the Settings attribute holding the limit


def _build_rules() -> list[RateRule]:
    return [
        RateRule(
            pattern=re.compile(r"^/api/v1/auth/login(/.*)?$"),
            scope="auth_login",
            limit_setting="RATE_LIMIT_LOGIN_PER_IP",
        ),
        RateRule(
            pattern=re.compile(r"^/api/v1/auth/refresh$"),
            scope="auth_refresh",
            limit_setting="RATE_LIMIT_REFRESH_PER_IP",
        ),
        RateRule(
            pattern=re.compile(r"^/api/v1/auth/register$"),
            scope="auth_register",
            limit_setting="RATE_LIMIT_REGISTER_PER_IP",
        ),
        RateRule(
            pattern=re.compile(r"^/api/v1/.*"),
            scope="api_default",
            limit_setting="RATE_LIMIT_API_DEFAULT_PER_IP",
        ),
    ]


EXEMPT_PATH_PREFIXES: tuple[str, ...] = (
    "/livez",
    "/readyz",
    "/metrics",
    "/health",
    "/static/",
    "/docs",
    "/redoc",
    "/openapi",
)


AUTH_FAILURE_PATHS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^/api/v1/auth/login(/.*)?$"),
    re.compile(r"^/api/v1/auth/refresh$"),
)


def is_auth_failure_path(path: str) -> bool:
    return any(p.match(path) for p in AUTH_FAILURE_PATHS)


def apply_rate_limit_headers(response, rate_result: RateLimitResult) -> None:
    """Inject ``X-RateLimit-*`` headers on the given response (idempotent)."""
    for name, value in rate_result.to_headers().items():
        response.headers.setdefault(name, value)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class SecurityRateLimitMiddleware(BaseHTTPMiddleware):
    PROBLEM_BASE: ClassVar[str] = "https://errors.vanguardops.dev"

    def __init__(self, app):
        super().__init__(app)
        settings = get_settings()
        self._enabled = settings.RATE_LIMIT_ENABLED
        self._trust_proxy = settings.TRUST_PROXY
        self._whitelist = self._compile_whitelist(settings.RATE_LIMIT_WHITELIST_CIDRS)
        self._rules = _build_rules()
        self._window = settings.RATE_LIMIT_WINDOW_SECONDS

    @staticmethod
    def _compile_whitelist(cidrs: list[str]):
        compiled = []
        for raw in cidrs:
            try:
                compiled.append(ipaddress.ip_network(raw, strict=False))
            except ValueError as exc:
                logger.warning("rate_limit_invalid_cidr_skipped", cidr=raw, error=str(exc))
        return compiled

    async def dispatch(self, request: Request, call_next):
        if not self._enabled:
            return await call_next(request)

        path = request.url.path
        if path.startswith(EXEMPT_PATH_PREFIXES):
            return await call_next(request)

        client_ip = self._extract_ip(request)
        request.state.client_ip = client_ip

        if self._is_whitelisted(client_ip):
            return await call_next(request)

        banlist = get_banlist()
        ban = banlist.is_banned(client_ip)
        if ban.banned:
            return self._reject(
                request,
                status=429,
                code="ip_banned",
                title="IP Address Banned",
                detail=(
                    "Your IP address has been temporarily banned for repeated "
                    "abuse. Try again later."
                ),
                retry_after=ban.retry_after_seconds,
                extra={"reason": ban.reason},
            )

        rule = self._match_rule(path)
        rate_result: RateLimitResult | None = None
        if rule is not None:
            settings = get_settings()
            limit = getattr(settings, rule.limit_setting)
            rate_result = get_rate_limiter().check(
                scope=rule.scope,
                identifier=client_ip,
                limit=limit,
                window_seconds=self._window,
            )
            request.state.rate_limit_result = rate_result
            if not rate_result.allowed:
                return self._reject(
                    request,
                    status=429,
                    code="rate_limited",
                    title="Too Many Requests",
                    detail="Rate limit exceeded for this endpoint.",
                    retry_after=rate_result.retry_after_seconds,
                    extra={"scope": rule.scope, "limit": rate_result.limit},
                    headers=rate_result.to_headers(),
                )

        # Modern Starlette returns the exception-handler's response from
        # ``call_next`` (rather than re-raising), so the status check below
        # works for both routes that returned normally and routes that
        # raised a domain error.
        response = await call_next(request)
        if rate_result is not None:
            apply_rate_limit_headers(response, rate_result)

        # Track abuse signals based on the actual status emitted.
        status = response.status_code
        if status == 401 and is_auth_failure_path(path):
            banlist.track_auth_failure(client_ip)
        elif status == 404:
            banlist.track_scan(client_ip)

        return response

    # --- helpers ------------------------------------------------------

    def _extract_ip(self, request: Request) -> str:
        if self._trust_proxy:
            forwarded = request.headers.get("X-Forwarded-For", "")
            if forwarded:
                first_hop = forwarded.split(",")[0].strip()
                if first_hop:
                    return first_hop
        return request.client.host if request.client else "unknown"

    def _is_whitelisted(self, ip: str) -> bool:
        if not self._whitelist:
            return False
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in net for net in self._whitelist)

    def _match_rule(self, path: str) -> RateRule | None:
        for rule in self._rules:
            if rule.pattern.match(path):
                return rule
        return None

    def _reject(
        self,
        request: Request,
        *,
        status: int,
        code: str,
        title: str,
        detail: str,
        retry_after: int,
        extra: dict | None = None,
        headers: dict | None = None,
    ) -> JSONResponse:
        body = {
            "type": f"{self.PROBLEM_BASE}/{code}",
            "title": title,
            "status": status,
            "detail": detail,
            "code": code,
            "instance": str(request.url.path),
        }
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            body["request_id"] = request_id
        if extra:
            body.update(extra)

        out_headers = {"Retry-After": str(max(1, retry_after))}
        if headers:
            out_headers.update(headers)

        logger.info(
            "request_throttled",
            code=code,
            ip=getattr(request.state, "client_ip", None),
            path=request.url.path,
            retry_after=retry_after,
        )
        return JSONResponse(
            status_code=status,
            content=body,
            media_type="application/problem+json",
            headers=out_headers,
        )
