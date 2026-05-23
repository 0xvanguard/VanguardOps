"""Structured logging using :mod:`structlog`.

Two output formats are supported:

* ``json``    - one JSON object per line, ideal for shipping to log aggregators.
* ``console`` - colorized, human-readable, used in local development.

Every log record is automatically enriched with the contextual ``request_id``
set by :class:`app.core.middleware.RequestContextMiddleware`, enabling
end-to-end correlation between API requests, service calls and Celery tasks.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.config import get_settings


def configure_logging() -> None:
    """Configure stdlib ``logging`` and ``structlog`` for the whole process.

    Idempotent: safe to call multiple times.
    """
    settings = get_settings()
    level = getattr(logging, settings.LOG_LEVEL)

    # Stdlib root logger - structlog will route through it.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
        force=True,
    )

    # Quiet down noisy third-party loggers.
    for noisy in ("uvicorn.access", "sqlalchemy.engine.Engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.LOG_FORMAT == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a :class:`structlog` logger bound to the given module name."""
    return structlog.get_logger(name)
