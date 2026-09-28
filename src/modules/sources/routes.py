"""Sources API routes (MariaDB)."""

import json
import logging
from typing import Any

import aiomysql
from fastapi import APIRouter, Depends, HTTPException

from src.database import fetchall, get_db
from src.models import ScanLog, ScanSource

from . import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[ScanSource])
async def list_sources(conn: aiomysql.Connection = Depends(get_db)) -> list[ScanSource]:
    """List all scan sources.

    Returns:
        List of scan sources.
    """
    sources = await service.list_sources(conn)
    return [ScanSource(**s) for s in sources]


@router.post("", response_model=ScanSource)
async def create_source(
    source: ScanSource,
    conn: aiomysql.Connection = Depends(get_db),
) -> ScanSource:
    """Create a new scan source.

    Args:
        source: Source configuration.
        conn: Database connection.

    Returns:
        Created source with ID.
    """
    try:
        source_id = await service.create_source(
            conn=conn,
            name=source.name,
            source_type=source.source_type,
            config=source.config,
            enabled=source.enabled,
            recursive=source.recursive,
            auto_tag=source.auto_tag,
            cron_schedule=source.cron_schedule,
        )
        created = await service.get_source(conn, source_id)
        if created:
            return ScanSource(**created)
        raise HTTPException(status_code=500, detail="Failed to create source")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{source_id}", response_model=ScanSource)
async def get_source(source_id: int, conn: aiomysql.Connection = Depends(get_db)) -> ScanSource:
    """Get source by ID.

    Args:
        source_id: Source ID.
        conn: Database connection.

    Returns:
        Source details.
    """
    source = await service.get_source(conn, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return ScanSource(**source)


@router.put("/{source_id}", response_model=ScanSource)
async def update_source(
    source_id: int,
    update: dict[str, Any],
    conn: aiomysql.Connection = Depends(get_db),
) -> ScanSource:
    """Update source configuration.

    Args:
        source_id: Source ID.
        update: Fields to update.
        conn: Database connection.

    Returns:
        Updated source.
    """
    updated = await service.update_source(conn, source_id, **update)
    if not updated:
        raise HTTPException(status_code=404, detail="Source not found")
    source = await service.get_source(conn, source_id)
    if source:
        return ScanSource(**source)
    raise HTTPException(status_code=500, detail="Failed to fetch updated source")


@router.delete("/{source_id}")
async def delete_source(source_id: int, conn: aiomysql.Connection = Depends(get_db)) -> dict[str, str]:
    """Delete source by ID.

    Args:
        source_id: Source ID.
        conn: Database connection.

    Returns:
        Deletion confirmation.
    """
    if not await service.delete_source(conn, source_id):
        raise HTTPException(status_code=404, detail="Source not found")
    return {"status": "deleted", "id": str(source_id)}


@router.post("/{source_id}/toggle")
async def toggle_source(source_id: int, enabled: bool, conn: aiomysql.Connection = Depends(get_db)) -> ScanSource:
    """Enable or disable a source.

    Args:
        source_id: Source ID.
        enabled: New state.
        conn: Database connection.

    Returns:
        Updated source.
    """
    if not await service.toggle_source(conn, source_id, enabled):
        raise HTTPException(status_code=404, detail="Source not found")
    source = await service.get_source(conn, source_id)
    if source:
        return ScanSource(**source)
    raise HTTPException(status_code=500, detail="Failed to fetch toggled source")


@router.get("/{source_id}/logs", response_model=list[ScanLog])
async def get_source_logs(source_id: int, conn: aiomysql.Connection = Depends(get_db)) -> list[ScanLog]:
    """Get scan logs for a source.

    Args:
        source_id: Source ID.
        conn: Database connection.

    Returns:
        List of scan logs (50 most recent).
    """
    rows = await fetchall(
        conn,
        """SELECT id, source_id, started_at, finished_at, files_found,
                  files_imported, files_skipped, errors_json
           FROM ml_scan_logs
           WHERE source_id = %s
           ORDER BY started_at DESC
           LIMIT 50""",
        (source_id,),
    )

    return [
        ScanLog(
            id=r["id"],
            source_id=r["source_id"],
            started_at=r["started_at"],
            finished_at=r["finished_at"],
            files_found=r["files_found"],
            files_imported=r["files_imported"],
            files_skipped=r["files_skipped"],
            errors=json.loads(r.get("errors_json", "[]")),
        )
        for r in rows
    ]
