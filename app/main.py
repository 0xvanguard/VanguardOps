"""FastAPI application factory.

Wires up:

* configuration & structured logging (must be first),
* CORS, security headers, request-id correlation,
* Prometheus metrics middleware + /metrics endpoint,
* RFC 7807 error handlers,
* the v1 API router and a minimal static frontend.

The factory pattern (``create_app``) keeps the module import-safe for tests.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from app.api.endpoints.health import router as health_router
from app.api.router import api_router
from app.bootstrap import bootstrap_admin
from app.core.config import get_settings
from app.core.error_handlers import register_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.middleware_security import SecurityRateLimitMiddleware
from app.core.observability import PrometheusMiddleware
from app.schemas.common import ProblemDetails

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup hooks (logging, bootstrap admin).

    Schema management is **never** performed at API startup. Production and
    development environments must run ``alembic upgrade head`` separately
    (the docker-compose API service does it before launching uvicorn). The
    test suite owns its own schema setup in ``tests/conftest.py``.
    """
    configure_logging()
    settings = get_settings()
    logger = get_logger(__name__)

    if not settings.is_test:
        try:
            bootstrap_admin()
        except Exception:  # pragma: no cover - first start may race
            logger.exception("bootstrap_admin_failed")

    logger.info(
        "application_started",
        environment=settings.ENVIRONMENT,
        version=settings.VERSION,
    )
    yield
    logger.info("application_shutting_down")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    app = FastAPI(
        title=f"{settings.PROJECT_NAME} API",
        description=(
            "Enterprise-grade IT support automation platform. "
            "Centralizes asset inventory, intelligent ticket triage and "
            "asynchronous workflow execution with a fully auditable trail."
        ),
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
        responses={
            400: {"model": ProblemDetails, "description": "Bad Request"},
            401: {"model": ProblemDetails, "description": "Unauthorized"},
            403: {"model": ProblemDetails, "description": "Forbidden"},
            404: {"model": ProblemDetails, "description": "Not Found"},
            409: {"model": ProblemDetails, "description": "Conflict"},
            422: {"model": ProblemDetails, "description": "Validation Error"},
            429: {"model": ProblemDetails, "description": "Too Many Requests"},
        },
    )

    # --- Middlewares (order matters: outermost added last) ---
    # Innermost (closest to the app) at the top, outermost at the bottom.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(PrometheusMiddleware)
    # SecurityRateLimit sits inside RequestContext so it can log with
    # ``request_id`` already bound, but outside Prometheus / SecurityHeaders
    # so a 429 short-circuit does not pollute latency histograms.
    app.add_middleware(SecurityRateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # --- Error handlers ---
    register_error_handlers(app)

    # --- Routers ---
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    app.include_router(health_router)

    # --- Static frontend (best-effort, no failure if dir is missing) ---
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(str(STATIC_DIR / "index.html"))

    # --- Legacy alias for the old /health endpoint ---
    @app.get("/health", include_in_schema=False)
    def legacy_health():
        return {
            "status": "ok",
            "service": f"{settings.PROJECT_NAME} API",
        }

    return app


app = create_app()
