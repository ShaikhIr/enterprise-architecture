"""Celery application configuration.

Constructs the shared Celery app used for the scheduled master-data jobs
(Agreement daily expiry and Mapping end-of-day expiry — Requirements 13.4 and
15). This module builds the app, lists the task modules to import so workers
can discover the tasks, and wires the periodic *beat schedule* for the two
expiry sweeps.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from src.config.settings import settings

# The task modules are listed in ``include`` so both the worker and the beat
# scheduler import and register them on startup. Importing a task module must be
# side-effect free with respect to the database (the tasks open sessions lazily
# at run time), so listing them here is safe.
celery_app = Celery(
    "lacm_masters",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BROKER_URL,
    include=[
        "src.infrastructure.background.schedulers.periodic_tasks",
        "src.infrastructure.background.tasks.mapping_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Re-deliver a task to another worker if the current one dies mid-run; safe
    # because the expiry jobs are idempotent.
    task_acks_late=True,
    # Periodic beat schedule for the master-data expiry sweeps. Both jobs are
    # idempotent and run as the ``system`` audit actor.
    beat_schedule={
        # Daily Agreement expiry sweep (Requirement 13.4): runs just after
        # midnight UTC so Agreements whose To Date has passed are expired at the
        # start of the new day.
        "masters-expire-due-agreements-daily": {
            "task": "masters.expire_due_agreements",
            "schedule": crontab(hour=0, minute=5),
        },
        # End-of-day Vendor-Customer Mapping expiry (Requirements 15.1, 15.2):
        # runs at the end of the UTC day to expire Mappings past their Validity
        # To date.
        "masters-expire-due-mappings-end-of-day": {
            "task": "masters.expire_due_mappings",
            "schedule": crontab(hour=23, minute=55),
        },
    },
)
