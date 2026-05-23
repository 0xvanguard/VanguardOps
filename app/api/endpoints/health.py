"""Liveness, readiness and Prometheus metrics endpoints.

The split between ``/livez`` and ``/readyz`` follows the
`Kubernetes probes pattern <https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/>`_:

* **Liveness** answers "is the process up?". It must never depend on
  external systems - failing it triggers a *restart*.
* **Readiness** answers "should I receive traffic?". It checks that
  every dependency the process needs (DB, Redis) is reachable - failing
  it removes the pod from the Service load balancer.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbSession
from app.core.config import get_settings
from app.schemas.common import HealthStatus, ReadinessStatus

router = APIRouter()


@router.get(
    "/livez",
    response_model=HealthStatus,
    summary="Liveness probe (process is up)",
    tags=["health"],
)
def livez() -> HealthStatus:
    settings = get_settings()
    return HealthStatus(status="ok", service=settings.PROJECT_NAME, version=settings.VERSION)


@router.get(
    "/readyz",
    response_model=ReadinessStatus,
    summary="Readiness probe (dependencies reachable)",
    tags=["health"],
)
def readyz(db: DbSession) -> ReadinessStatus:
    checks: dict[str, str] = {}
    overall = "ready"

    # Database
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except SQLAlchemyError as exc:  # pragma: no cover - integration concern
        checks["database"] = f"error: {exc.__class__.__name__}"
        overall = "not_ready"

    # Redis (best effort: only check when not in test mode)
    settings = get_settings()
    if not settings.is_test:
        try:
            from redis import Redis

            client = Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=1)
            client.ping()
            checks["redis"] = "ok"
        except Exception as exc:  # pragma: no cover - integration concern
            checks["redis"] = f"error: {exc.__class__.__name__}"
            overall = "not_ready"

    return ReadinessStatus(status=overall, checks=checks)


@router.get(
    "/metrics",
    summary="Prometheus exposition format metrics",
    tags=["health"],
    response_class=Response,
)
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
