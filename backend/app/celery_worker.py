from os import getenv
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "jobfit",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.cheatsheet_tasks"],
)

celery_app.conf.update(task_track_started=True, result_expires=3600)
