import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers.clusters import router as clusters_router
from app.routers.digest import router as digest_router
from app.routers.items import router as items_router
from app.scheduler import configure_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: sweep stuck items, start scheduler. Shutdown: stop scheduler."""
    from app.services.worker import sweep_stuck_items

    # Start scheduler
    scheduler = configure_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler

    # Sweep stuck/failed items
    try:
        asyncio.create_task(sweep_stuck_items())
        logger.info("Startup sweep task created")
    except Exception as e:
        logger.error(f"Failed to start sweep task: {e}")

    yield

    # Shutdown
    scheduler.shutdown()


app = FastAPI(title="Insight", version="0.1.0", lifespan=lifespan)
app.include_router(items_router)
app.include_router(digest_router)
app.include_router(clusters_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
