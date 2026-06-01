"""Sources API routes."""

import logging
from typing import Any

from aiosqlite import Connection
from fastapi import APIRouter, Depends, HTTPException

from src.database import get_db
from src.models import ScanSource
from . import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[ScanSource])
async def list_sources(
    db: Connection = Depends(get_db),
) -> list[ScanSource]:
    """List all scan sources.

    Returns:
        List of scan sources.
    """
    sources = await service.list_sources(db)
    return [ScanSource(**s) for s in sources]


@router.post("", response_model=ScanSource)
async def create_source(
    source: ScanSource,
    db: Connection = Depends(get_db),
) -> ScanSource:
    """Create a new scan source.

    Args:
        source: Source configuration.
        db: Database connection.

    Returns:
        Created source with ID.
    """
    try:
        source_id = await service.create_source(
            db=db,
            name=source.name,
            source_type=source.source_type,
            config=source.config,
            enabled=source.enabled,
            recursive=source.recursive,
            auto_tag=source.auto_tag,
            cron_schedule=source.cron_schedule,
        )

        # Fetch and return created source
        created = await service.get_source(db, source_id)
        if created:
            return ScanSource(**created)
        else:
            raise HTTPException(status_code=500, detail="Failed to create source")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Create source failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{source_id}", response_model=ScanSource)
async def get_source(
    source_id: int,
    db: Connection = Depends(get_db),
) -> ScanSource:
    """Get source by ID.

    Args:
        source_id: Source ID.
        db: Database connection.

    Returns:
        Source details.

    Raises:
        HTTPException: If not found.
    """
    source = await service.get_source(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    return ScanSource(**source)


@router.put("/{source_id}", response_model=ScanSource)
async def update_source(
    source_id: int,
    update: dict[str, Any],
    db: Connection = Depends(get_db),
) -> ScanSource:
    """Update source configuration.

    Args:
        source_id: Source ID.
        update: Fields to update.
        db: Database connection.

    Returns:
        Updated source.

    Raises:
        HTTPException: If not found.
    """
    updated = await service.update_source(db, source_id, **update)
    if not updated:
        raise HTTPException(status_code=404, detail="Source not found")

    source = await service.get_source(db, source_id)
    if source:
        return ScanSource(**source)
    else:
        raise HTTPException(status_code=500, detail="Failed to fetch updated source")


@router.delete("/{source_id}")
async def delete_source(
    source_id: int,
    db: Connection = Depends(get_db),
) -> dict[str, str]:
    """Delete source by ID.

    Args:
        source_id: Source ID.
        db: Database connection.

    Returns:
        Deletion confirmation.

    Raises:
        HTTPException: If not found.
    """
    deleted = await service.delete_source(db, source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Source not found")

    return {"status": "deleted", "id": str(source_id)}


@router.post("/{source_id}/toggle")
async def toggle_source(
    source_id: int,
    enabled: bool,
    db: Connection = Depends(get_db),
) -> ScanSource:
    """Enable or disable a source.

    Args:
        source_id: Source ID.
        enabled: New state.
        db: Database connection.

    Returns:
        Updated source.

    Raises:
        HTTPException: If not found.
    """
    toggled = await service.toggle_source(db, source_id, enabled)
    if not toggled:
        raise HTTPException(status_code=404, detail="Source not found")

    source = await service.get_source(db, source_id)
    if source:
        return ScanSource(**source)
    else:
        raise HTTPException(status_code=500, detail="Failed to fetch toggled source")
