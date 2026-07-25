from celery import Celery
from app.config import settings

# Initialize global celery application
celery_app = Celery(
    "leadradar",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks"]
)

# Apply common configurations
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True
)

# Define optional celery beat schedules for periodic scraping
celery_app.conf.beat_schedule = {
    "fetch-and-match-leads-every-5-min": {
        "task": "app.tasks.fetch_and_match_leads_task",
        "schedule": float(settings.POLL_INTERVAL_SECONDS) if settings.POLL_INTERVAL_SECONDS else 300.0
    }
}
