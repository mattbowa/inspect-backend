from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "seo_agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600,
    beat_schedule={
        "daily-automated-scans": {
            "task": "tasks.run_scheduled_scans",
            # "schedule": crontab(hour=6, minute=0),  # 6am UTC = 4pm Sydney (AEST) / 6pm Sydney (AEDT)
            "schedule": crontab(minute="*/10"),  # TEST: runs every 10 minutes
        },
    },
)
