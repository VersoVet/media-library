"""Search API routes (Digikam-compatible)."""

import logging
from typing import Any

import aiomysql
from fastapi import APIRouter, Depends, HTTPException, Query

from src.database import IMAGE_CATEGORY_IMAGE, get_db
from src.models import MediaItem, SearchResult

from . import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["search"])


def _row_to_media_item(row: dict[str, Any]) -> MediaItem:
    """Convert enriched row to MediaItem."""
    media_type = "image" if row.get("category") == IMAGE_CATEGORY_IMAGE else "video"
    return MediaItem(
        id=row["id"],
        name=row.get("name", ""),
        title=row.get("title", row.get("name", "")),
        description=row.get("description", ""),
        media_type=media_type,
        mime_type=row.get("mime_type", ""),
        album_id=row.get("album"),
        album_path=row.get("album_path"),
        storage_backend=row.get("storage_backend", "nas"),
        storage_path=row.get("storage_path"),
        file_size=row.get("fileSize", 0),
        unique_hash=row.get("uniqueHash"),
        width=row.get("width"),
        height=row.get("height"),
        rating=row.get("rating"),
        tags=row.get("tags", []),
        created_at=row.get("creationDate"),
        updated_at=row.get("modificationDate"),
    )


@router.get("/search", response_model=SearchResult)
async def search_media(
    q: str = Query(""),
    media_type: str | None = Query(None),
    album_id: int | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: aiomysql.Connection = Depends(get_db),
) -> SearchResult:
    """Search media or list all if query is empty.

    Args:
        q: Search query.
        media_type: Filter by 'image' or 'video'.
        album_id: Filter by album ID.
        limit: Max results.
        offset: Result offset.
        conn: Database connection.

    Returns:
        Search results with total count.
    """
    try:
        if not q:
            results, total = await service.list_all_media(conn, media_type, album_id, limit, offset)
        else:
            results, total = await service.search(conn, q, media_type, album_id, limit, offset)

        items = [_row_to_media_item(row) for row in results]
        return SearchResult(total=total, items=items)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tags")
async def list_tags(
    conn: aiomysql.Connection = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all tags with media count.

    Args:
        conn: Database connection.

    Returns:
        List of tags with id, name, pid, count.
    """
    try:
        return await service.get_all_tags(conn)
    except Exception as e:
        logger.error(f"List tags failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tags/{tag_name}/media", response_model=SearchResult)
async def get_media_by_tag(
    tag_name: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: aiomysql.Connection = Depends(get_db),
) -> SearchResult:
    """Get media for a specific tag.

    Args:
        tag_name: Tag name.
        limit: Max results.
        offset: Result offset.
        conn: Database connection.

    Returns:
        Media items with the tag.
    """
    try:
        media_list, total = await service.get_media_by_tag(conn, tag_name, limit, offset)
        items = [_row_to_media_item(row) for row in media_list]
        return SearchResult(total=total, items=items)
    except Exception as e:
        logger.error(f"Get media by tag failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
