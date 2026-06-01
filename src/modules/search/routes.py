"""Search API routes."""

import logging
from typing import Any

from aiosqlite import Connection
from fastapi import APIRouter, Depends, HTTPException, Query

from src.database import get_db
from src.models import SearchResult

from . import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search", response_model=SearchResult)
async def search(
    q: str = Query(""),
    media_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Connection = Depends(get_db),
) -> SearchResult:
    """Search media by FTS5.

    Args:
        q: Search query.
        media_type: Filter by 'image' or 'video'.
        limit: Max results.
        offset: Result offset.
        db: Database connection.

    Returns:
        Search results with total count.
    """
    if not q:
        raise HTTPException(status_code=400, detail="Query string required")

    try:
        from datetime import datetime

        from src.models import MediaItem, MediaMetadata

        results, total = await service.search(db, q, media_type, limit, offset)

        media_items = []
        for row in results:
            item = MediaItem(
                id=row["id"],
                title=row["title"],
                description=row.get("description", ""),
                media_type=row["media_type"],
                mime_type=row["mime_type"],
                dropbox_path=row["dropbox_path"],
                source_id=row.get("source_id"),
                source_path=row.get("source_path"),
                file_size=row["file_size"],
                metadata=MediaMetadata(
                    width=row.get("width"),
                    height=row.get("height"),
                    duration_seconds=row.get("duration_seconds"),
                    exif=row.get("metadata", {}).get("exif", {}),
                ),
                tags=row.get("tags", []),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            media_items.append(item)

        return SearchResult(total=total, items=media_items)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tags")
async def list_tags(
    db: Connection = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all tags with media count.

    Returns:
        List of tags with id, name, count.
    """
    try:
        tags = await service.get_all_tags(db)
        return tags
    except Exception as e:
        logger.error(f"List tags failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tags/{tag_name}/media")
async def get_media_by_tag(
    tag_name: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Connection = Depends(get_db),
) -> SearchResult:
    """Get media for a specific tag.

    Args:
        tag_name: Tag name.
        limit: Max results.
        offset: Result offset.
        db: Database connection.

    Returns:
        Media items with the tag.
    """
    try:
        from datetime import datetime

        from src.models import MediaItem, MediaMetadata

        media_list, total = await service.get_media_by_tag(db, tag_name, limit, offset)

        media_items = []
        for row in media_list:
            item = MediaItem(
                id=row["id"],
                title=row["title"],
                description=row.get("description", ""),
                media_type=row["media_type"],
                mime_type=row["mime_type"],
                dropbox_path=row["dropbox_path"],
                source_id=row.get("source_id"),
                source_path=row.get("source_path"),
                file_size=row["file_size"],
                metadata=MediaMetadata(
                    width=row.get("width"),
                    height=row.get("height"),
                    duration_seconds=row.get("duration_seconds"),
                    exif=row.get("metadata", {}).get("exif", {}),
                ),
                tags=row.get("tags", []),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            media_items.append(item)

        return SearchResult(total=total, items=media_items)

    except Exception as e:
        logger.error(f"Get media by tag failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
