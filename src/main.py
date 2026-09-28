"""Media Library v2 - Main FastAPI application (Digikam + NAS)."""

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

from src.database import check_health, close_db, get_db_context, init_db, release_db_context
from src.models import HealthResponse, InfoResponse
from src.modules.catalog import files_routes as files_routes
from src.modules.catalog import routes as catalog_routes
from src.modules.scanner import routes as scanner_routes
from src.modules.search import routes as search_routes
from src.modules.sources import routes as sources_routes
from src.modules.storage.registry import get_default, init_backends, list_backends
from src.modules.tagger import routes as tagger_routes
from src.modules.thumbnails import routes as thumbnail_routes

logger = logging.getLogger(__name__)

scheduler = None
onyx = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context for startup and shutdown."""
    global scheduler, onyx
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    # Initialize OnyxClient
    if OnyxClient:
        try:
            onyx = OnyxClient()
            onyx.start()
            try:
                onyx.status("UP")
            except (AttributeError, TypeError):
                pass
            logger.info("OnyxClient initialized")
        except Exception as e:
            logger.error(f"Failed to start OnyxClient: {e}")
            onyx = None

    # Initialize storage backends
    logger.info("Initializing storage backends...")
    init_backends()
    logger.info(f"Storage backends: {list_backends()}")

    # Initialize database
    logger.info("Initializing MariaDB connection pool...")
    await init_db()

    # Start scheduler
    logger.info("Starting APScheduler...")
    scheduler = AsyncIOScheduler()

    conn = None
    try:
        conn = await get_db_context()
        from src.modules.sources import service as sources_service

        sources = await sources_service.list_sources(conn)
        for source in sources:
            if source.get("enabled", False):
                cron_schedule = source.get("cron_schedule", "0 */6 * * *")
                cron_parts = cron_schedule.split()
                if len(cron_parts) != 5:
                    logger.warning(f"Invalid cron for source {source['id']}: {cron_schedule}")
                    continue
                minute, hour, day, month, day_of_week = cron_parts
                try:
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
                    logger.info(f"Scheduled scan for source {source['id']}: {cron_schedule}")
                except Exception as job_err:
                    logger.warning(f"Failed to schedule source {source['id']}: {job_err}")
    except Exception as e:
        logger.error(f"Failed to load sources for scheduling: {e}")
    finally:
        if conn:
            await release_db_context(conn)

    scheduler.start()

    yield

    # Shutdown
    if scheduler:
        scheduler.shutdown()
    await close_db()

    if onyx:
        try:
            onyx.status("DOWN")
            onyx.stop()
        except Exception:
            pass


async def _scan_source_scheduled(source_id: int) -> None:
    """Scan a source (scheduled task).

    Args:
        source_id: Source ID to scan.
    """
    conn = None
    try:
        conn = await get_db_context()
        from src.modules.scanner import service as scanner_service
        from src.modules.sources import service as sources_service

        source = await sources_service.get_source(conn, source_id)
        if source:
            logger.info(f"Running scheduled scan for source {source_id}")
            await scanner_service.scan_source(conn, source)
    except Exception as e:
        logger.error(f"Scheduled scan failed for source {source_id}: {e}")
    finally:
        if conn:
            await release_db_context(conn)


# Create FastAPI app
app = FastAPI(
    title="Media Library",
    description="Image and video library with Digikam-compatible database and NAS storage",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(catalog_routes.router)
app.include_router(files_routes.router)
app.include_router(tagger_routes.router)
app.include_router(thumbnail_routes.router)
app.include_router(search_routes.router)
app.include_router(sources_routes.router)
app.include_router(scanner_routes.router)

# Albums and integrations routers (lazy import to avoid circular)
try:
    from src.modules.albums import routes as albums_routes

    app.include_router(albums_routes.router)
except ImportError:
    logger.debug("Albums module not yet available")

try:
    from src.modules.integrations import routes as integrations_routes

    app.include_router(integrations_routes.router)
except ImportError:
    logger.debug("Integrations module not yet available")

# Mount static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint.

    Returns:
        Health status with DB and storage status.
    """
    db_health = await check_health()
    db_status = db_health.get("status", "error")

    nas_mounted = False
    try:
        nas = get_default()
        nas_mounted = hasattr(nas, "is_mounted") and nas.is_mounted()
    except Exception:
        pass

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        db=db_status,
        storage=",".join(list_backends()),
        nas_mounted=nas_mounted,
    )


@app.get("/info", response_model=InfoResponse)
async def info() -> InfoResponse:
    """Get skill info.

    Returns:
        Info with counts and storage backend.
    """
    try:
        from src.database import fetchone

        conn = await get_db_context()

        media_row = await fetchone(conn, "SELECT COUNT(*) as cnt FROM Images WHERE status = 1")
        tag_row = await fetchone(conn, "SELECT COUNT(*) as cnt FROM Tags WHERE pid >= 0")
        album_row = await fetchone(conn, "SELECT COUNT(*) as cnt FROM Albums")
        source_row = await fetchone(conn, "SELECT COUNT(*) as cnt FROM ml_scan_sources")

        await release_db_context(conn)

        return InfoResponse(
            version="2.0.0",
            total_media=media_row["cnt"] if media_row else 0,
            total_tags=tag_row["cnt"] if tag_row else 0,
            total_albums=album_row["cnt"] if album_row else 0,
            total_sources=source_row["cnt"] if source_row else 0,
            storage_backend=",".join(list_backends()),
        )
    except Exception as e:
        logger.error(f"Info endpoint failed: {e}")
        return InfoResponse(
            total_media=0,
            total_tags=0,
            total_albums=0,
            total_sources=0,
            storage_backend="error",
        )


@app.get("/cron")
async def cron_status() -> dict[str, Any]:
    """Get cron scheduler status.

    Returns:
        Scheduler status with job info.
    """
    if not scheduler:
        return {"status": "disabled", "tasks": []}
    try:
        jobs = scheduler.get_jobs()
        return {
            "status": "running",
            "jobs_count": len(jobs),
            "tasks": [{"id": j.id, "next_run_time": str(j.next_run_time)} for j in jobs],
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "tasks": []}


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint.

    Returns:
        Welcome message with links.
    """
    return {
        "message": "Media Library API v2.0",
        "docs": "/docs",
        "health": "/health",
        "info": "/info",
        "dashboard": "/static/",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8202, reload=False)
