"""Media Library - Main FastAPI application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

try:
    from onyx_sdk import OnyxClient
except ImportError:
    OnyxClient = None

from src.database import get_db_context, init_db
from src.models import HealthResponse, InfoResponse
from src.modules.catalog import routes as catalog_routes
from src.modules.dropbox import service as dropbox_service
from src.modules.scanner import routes as scanner_routes
from src.modules.scanner import service as scanner_service
from src.modules.search import routes as search_routes
from src.modules.sources import routes as sources_routes
from src.modules.tagger import routes as tagger_routes
from src.modules.thumbnails import routes as thumbnail_routes

logger = logging.getLogger(__name__)

# APScheduler for cron jobs
scheduler = None

# OnyxClient for skill status visibility
onyx = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context for startup and shutdown."""
    global scheduler, onyx
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    # Initialize OnyxClient - signal UP status
    if OnyxClient:
        try:
            logger.info("Initializing OnyxClient...")
            onyx = OnyxClient()
            onyx.start()
            logger.info("OnyxClient started - UP status")
        except Exception as e:
            logger.error(f"Failed to start OnyxClient: {e}", exc_info=True)
            onyx = None
    else:
        logger.warning("OnyxClient not available")

    logger.info("Initializing database...")
    await init_db()

    logger.info("Starting APScheduler...")
    scheduler = AsyncIOScheduler()

    # Load sources and add cron jobs
    try:
        db = await get_db_context()
        from src.modules.sources import service as sources_service

        sources = await sources_service.list_sources(db)
        for source in sources:
            if source.get("enabled", False):
                cron_schedule = source.get("cron_schedule", "0 */6 * * *")
                # Parse cron expression: minute hour day month day_of_week
                cron_parts = cron_schedule.split()
                if len(cron_parts) == 5:
                    minute, hour, day, month, day_of_week = cron_parts
                    # Add job for this source
                    scheduler.add_job(
                        _scan_source_scheduled,
                        "cron",
                        minute=minute,
                        hour=hour,
                        day=day,
                        month=month,
                        day_of_week=day_of_week,
                        args=[source["id"]],
                        id=f"scan_source_{source['id']}",
                        replace_existing=True,
                    )
                    logger.info(f"Scheduled cron scan for source {source['id']}: {cron_schedule}")
                else:
                    logger.warning(f"Invalid cron schedule for source {source['id']}: {cron_schedule}")

        await db.close()
    except Exception as e:
        logger.error(f"Failed to load sources for scheduling: {e}")

    scheduler.start()
    logger.info("APScheduler started")

    yield

    # Shutdown - signal DOWN status
    if scheduler:
        scheduler.shutdown()
        logger.info("APScheduler shutdown")

    if onyx:
        try:
            onyx.stop()
            logger.info("OnyxClient stopped")
        except Exception as e:
            logger.warning(f"Failed to stop OnyxClient: {e}")


async def _scan_source_scheduled(source_id: int) -> None:
    """Scan a source (scheduled task)."""
    try:
        db = await get_db_context()
        from src.modules.sources import service as sources_service

        source = await sources_service.get_source(db, source_id)
        if source:
            logger.info(f"Running scheduled scan for source {source_id}")
            # Signal WORKING status
            if onyx:
                try:
                    onyx.set_status("WORKING", f"Scanning source {source_id}")
                except Exception:
                    pass
            await scanner_service.scan_source(db, source)
        await db.close()
    except Exception as e:
        logger.error(f"Scheduled scan failed for source {source_id}: {e}")


# Create FastAPI app
app = FastAPI(
    title="Media Library",
    description="Image and video library with keyword classification",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (can be restricted)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers from modules
app.include_router(catalog_routes.router)
app.include_router(tagger_routes.router)
app.include_router(thumbnail_routes.router)
app.include_router(search_routes.router)
app.include_router(sources_routes.router)
app.include_router(scanner_routes.router)

# Mount static files (dashboard)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")


# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint.

    Returns:
        Health status.
    """
    try:
        db = await get_db_context()
        await db.execute("SELECT 1")
        await db.close()
        db_status = "ok"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "error"

    dropbox_status = None
    try:
        await dropbox_service.get_dropbox_token()
        dropbox_status = "ok"
    except Exception:
        dropbox_status = "unavailable"

    return HealthResponse(status="ok", db=db_status, dropbox=dropbox_status)


# Info endpoint
@app.get("/info", response_model=InfoResponse)
async def info() -> InfoResponse:
    """Get skill info.

    Returns:
        Info with media count, tags count, etc.
    """
    try:
        db = await get_db_context()

        # Count media
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM media")
        row = await cursor.fetchone()
        total_media = dict(row)["cnt"] if row else 0

        # Count tags
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM tags")
        row = await cursor.fetchone()
        total_tags = dict(row)["cnt"] if row else 0

        # Count sources
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM scan_sources")
        row = await cursor.fetchone()
        total_sources = dict(row)["cnt"] if row else 0

        await db.close()

    except Exception as e:
        logger.error(f"Info endpoint failed: {e}")
        total_media = 0
        total_tags = 0
        total_sources = 0

    return InfoResponse(
        version="1.0.0",
        total_media=total_media,
        total_tags=total_tags,
        total_sources=total_sources,
    )


# Cron status endpoint
@app.get("/cron")
async def cron_status() -> dict[str, Any]:
    """Get cron scheduler status.

    Returns:
        Scheduler status with running jobs and task definitions.
    """
    if not scheduler:
        return {"status": "disabled", "tasks": []}

    try:
        jobs = scheduler.get_jobs()
        tasks = [
            {
                "id": job.id,
                "next_run_time": str(job.next_run_time) if job.next_run_time else None,
            }
            for job in jobs
        ]
        return {
            "status": "running",
            "jobs_count": len(jobs),
            "tasks": tasks,
        }
    except Exception as e:
        logger.error(f"Failed to get cron status: {e}")
        return {"status": "error", "error": str(e), "tasks": []}


# Root endpoint
@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint.

    Returns:
        Welcome message.
    """
    return {
        "message": "Media Library API",
        "docs": "/docs",
        "health": "/health",
        "info": "/info",
        "dashboard": "/static/",
        "cron": "/cron",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8202,
        reload=False,
    )
