from celery import Celery
from kombu import Queue

from config import settings
from models.sqlite_config import is_sqlite_url

celery_app = Celery(
    "dragonlens",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["workers.tasks"],
)

def _celery_sqlite_concurrency(database_url: str) -> int | None:
    if is_sqlite_url(database_url):
        return 1
    return None


celery_config = {
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,
    "task_track_started": True,
    "task_time_limit": 3600,
    "task_soft_time_limit": 3000,
    "worker_prefetch_multiplier": 1,
    "worker_max_tasks_per_child": 100,
    "task_default_queue": settings.celery_queue_name,
    "task_default_exchange": settings.celery_queue_name,
    "task_default_routing_key": settings.celery_queue_name,
    "task_queues": (Queue(settings.celery_queue_name),),
}

sqlite_concurrency = _celery_sqlite_concurrency(settings.database_url)
if sqlite_concurrency is not None:
    celery_config["worker_concurrency"] = sqlite_concurrency

celery_app.conf.update(celery_config)

celery_app.conf.beat_schedule = {
}
