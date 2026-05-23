"""Celery application factory.

Tasks live in :mod:`app.workers.tasks`. Configuration mirrors the recommended
defaults from `Celery's docs
<https://docs.celeryq.dev/en/stable/userguide/configuration.html>`_:
explicit JSON serialization, UTC time, and bounded worker prefetch.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "vanguardops",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Test/dev convenience: when ``CELERY_TASK_ALWAYS_EAGER`` is true, tasks
    # run inline (no broker required).
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=settings.CELERY_TASK_ALWAYS_EAGER,
)
