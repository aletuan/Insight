"""
APScheduler configuration.

Two cron jobs:
- clustering_nightly: runs at 3:00 AM, rebuilds K-means clusters
- digest_daily: runs at 7:00 AM, generates the daily digest
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

logger = logging.getLogger(__name__)


async def _run_clustering_job():
    """Wrapper to run clustering in the scheduler context."""
    from app.services.clustering import run_clustering

    logger.info("Scheduler: starting nightly clustering")
    try:
        result = await run_clustering()
        if result:
            logger.info(f"Scheduler: clustering complete — {result}")
        else:
            logger.info("Scheduler: clustering skipped (below threshold)")
    except Exception:
        logger.exception("Scheduler: clustering failed")


async def _run_digest_job():
    """Wrapper to run digest generation in the scheduler context."""
    from app.services.digest import run_digest_generation

    logger.info("Scheduler: starting daily digest generation")
    try:
        result = await run_digest_generation()
        if result:
            logger.info(f"Scheduler: digest generated — {result}")
        else:
            logger.info("Scheduler: digest skipped (no new items)")
    except Exception:
        logger.exception("Scheduler: digest generation failed")


def configure_scheduler() -> AsyncIOScheduler:
    """
    Create and configure the APScheduler instance with both cron jobs.
    Call scheduler.start() separately (typically in FastAPI lifespan).
    """
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        _run_clustering_job,
        trigger=CronTrigger(hour=settings.clustering_hour, minute=0),
        id="clustering_nightly",
        name="Nightly K-means clustering",
        replace_existing=True,
    )

    scheduler.add_job(
        _run_digest_job,
        trigger=CronTrigger(hour=settings.digest_hour, minute=0),
        id="digest_daily",
        name="Daily digest generation",
        replace_existing=True,
    )

    return scheduler
