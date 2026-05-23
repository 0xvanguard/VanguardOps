"""Prometheus metric definitions and instrumentation middleware.

Exposes:

* ``http_requests_total`` (counter, labelled by method/path/status)
* ``http_request_duration_seconds`` (histogram of request durations)
"""

from __future__ import annotations

import time

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests handled by the API",
    labelnames=("method", "path", "status_code"),
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    labelnames=("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Increment counters / histograms on every request."""

    async def dispatch(self, request: Request, call_next):
        # Use the route template (e.g. ``/tickets/{ticket_id}``) when
        # available so we don't blow up cardinality with raw paths.
        method = request.method
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        path = request.scope.get("route").path if request.scope.get("route") else request.url.path  # type: ignore[union-attr]
        REQUEST_COUNT.labels(method=method, path=path, status_code=response.status_code).inc()
        REQUEST_LATENCY.labels(method=method, path=path).observe(elapsed)
        return response
