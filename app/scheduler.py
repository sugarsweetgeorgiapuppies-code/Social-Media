"""Scheduled daily research + briefing generation.

Uses APScheduler so a single owner can run everything from one process. The
daily job runs the same end-to-end workflow the 'Run research now' button uses.
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings
from .database import SessionLocal
from .logging_config import get_logger
from .services import briefing as briefing_svc

log = get_logger(__name__)
_scheduler: BackgroundScheduler | None = None


def _daily_job() -> None:
    log.info("Scheduled daily research starting...")
    with SessionLocal() as db:
        try:
            briefing_svc.run_daily_workflow(db, run_type="daily")
            db.commit()
            log.info("Scheduled daily research complete.")
        except Exception:
            db.rollback()
            log.exception("Scheduled daily research failed")


def start_scheduler() -> None:
    global _scheduler
    if not settings.DAILY_RUN_ENABLED:
        log.info("Daily scheduler disabled (DAILY_RUN_ENABLED=false).")
        return
    if _scheduler:
        return
    try:
        hour, minute = settings.DAILY_RUN_TIME.split(":")
        _scheduler = BackgroundScheduler(timezone=settings.TIMEZONE)
        _scheduler.add_job(
            _daily_job,
            CronTrigger(hour=int(hour), minute=int(minute)),
            id="daily_research",
            replace_existing=True,
        )
        _scheduler.start()
        log.info(
            "Daily research scheduled for %s %s.",
            settings.DAILY_RUN_TIME,
            settings.TIMEZONE,
        )
    except Exception:
        log.exception("Could not start scheduler")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
