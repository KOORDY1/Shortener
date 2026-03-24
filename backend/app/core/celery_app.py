from __future__ import annotations

from celery import Celery

from app.core.config import get_settings


settings = get_settings()


celery_app = Celery(
    "shorts_backend",
    broker=settings.celery_broker_url or settings.redis_url,
    backend=settings.celery_result_backend or settings.redis_url,
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
)

# Celery looks up `<package>.tasks` — use `app` so `app.tasks` (this package) loads.
celery_app.autodiscover_tasks(["app"])
