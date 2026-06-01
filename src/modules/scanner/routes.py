"""Scanner API routes."""

import logging

from aiosqlite import Connection
from fastapi import APIRouter, Depends, HTTPException

from src.database import get_db
from src.models import SyncReport

from . import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scanner", tags=["scanner"])


@router.post("/run", response_model=list[SyncReport])
async def run_scanner(
    db: Connection = Depends(get_db),
) -> list[SyncReport]:
    """Run scanner on all enabled sources.

    Args:
        db: Database connection.

    Returns:
        List of sync reports.
    """
    try:
        reports = await service.scan_all_enabled_sources(db)
        logger.info(f"Scanner completed with {len(reports)} sources")
        return reports
    except Exception as e:
        logger.error(f"Scanner failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/{source_id}", response_model=SyncReport)
async def run_source_scan(
    source_id: int,
    db: Connection = Depends(get_db),
) -> SyncReport:
    """Run scanner on a specific source.

    Args:
        source_id: Source ID.
        db: Database connection.

    Returns:
        Sync report.

    Raises:
        HTTPException: If source not found.
    """
    from src.modules.sources import service as sources_service

    source = await sources_service.get_source(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    try:
        report = await service.scan_source(db, source)
        return report
    except Exception as e:
        logger.error(f"Scan failed for source {source_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
