"""Albums API routes (Digikam-compatible)."""

import logging
from typing import Any

import aiomysql
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from src.database import get_db
from src.models import Album, AlbumCreate, SearchResult

from . import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/albums", tags=["albums"])


@router.post("", response_model=Album)
async def create_album(
    album: AlbumCreate,
    conn: aiomysql.Connection = Depends(get_db),
) -> Album:
    """Create a new album.

    Args:
        album: Album creation request.
        conn: Database connection.

    Returns:
        Created album.
    """
    album_id = await service.create_album(conn, relative_path=album.relative_path, caption=album.caption)
    result = await service.get_album(conn, album_id)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create album")
    return Album(
        id=result["id"],
        relative_path=result["relativePath"],
        caption=result.get("caption"),
        media_count=result.get("media_count", 0),
        date=result.get("date"),
    )


@router.get("")
async def list_albums(
    parent_path: str | None = Query(None),
    conn: aiomysql.Connection = Depends(get_db),
) -> list[Album]:
    """List albums.

    Args:
        parent_path: Filter to children of this path.
        conn: Database connection.

    Returns:
        List of albums.
    """
    albums = await service.list_albums(conn, parent_path)
    return [
        Album(
            id=a["id"],
            album_root=a.get("albumRoot", 1),
            relative_path=a["relativePath"],
            caption=a.get("caption"),
            media_count=a.get("media_count", 0),
            date=a.get("date"),
        )
        for a in albums
    ]


@router.get("/{album_id}", response_model=Album)
async def get_album(album_id: int, conn: aiomysql.Connection = Depends(get_db)) -> Album:
    """Get album details.

    Args:
        album_id: Album ID.
        conn: Database connection.

    Returns:
        Album with media count.
    """
    result = await service.get_album(conn, album_id)
    if not result:
        raise HTTPException(status_code=404, detail="Album not found")
    return Album(
        id=result["id"],
        album_root=result.get("albumRoot", 1),
        relative_path=result["relativePath"],
        caption=result.get("caption"),
        media_count=result.get("media_count", 0),
        date=result.get("date"),
    )


@router.put("/{album_id}")
async def update_album(
    album_id: int,
    caption: str = Body(...),
    conn: aiomysql.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Update album metadata.

    Args:
        album_id: Album ID.
        caption: New caption.
        conn: Database connection.

    Returns:
        Update confirmation.
    """
    if not await service.update_album(conn, album_id, caption=caption):
        raise HTTPException(status_code=404, detail="Album not found")
    return {"status": "updated", "id": album_id}


@router.delete("/{album_id}")
async def delete_album(album_id: int, conn: aiomysql.Connection = Depends(get_db)) -> dict[str, Any]:
    """Delete album (media moved to root, not deleted).

    Args:
        album_id: Album ID.
        conn: Database connection.

    Returns:
        Deletion confirmation.
    """
    if not await service.delete_album(conn, album_id):
        raise HTTPException(status_code=404, detail="Album not found")
    return {"status": "deleted", "id": album_id}


@router.get("/{album_id}/media", response_model=SearchResult)
async def get_album_media(
    album_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: aiomysql.Connection = Depends(get_db),
) -> SearchResult:
    """List media in an album.

    Args:
        album_id: Album ID.
        limit: Max results.
        offset: Result offset.
        conn: Database connection.

    Returns:
        Paginated media list.
    """
    from src.modules.search.routes import _row_to_media_item

    results, total = await service.get_album_media(conn, album_id, limit, offset)
    items = [_row_to_media_item(r) for r in results]
    return SearchResult(total=total, items=items)


@router.post("/{album_id}/media")
async def add_media_to_album(
    album_id: int,
    media_ids: list[int] = Body(...),
    conn: aiomysql.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Add media items to an album.

    Args:
        album_id: Target album.
        media_ids: List of image IDs to move.
        conn: Database connection.

    Returns:
        Result with count.
    """
    moved = 0
    for img_id in media_ids:
        if await service.add_media_to_album(conn, album_id, img_id):
            moved += 1
    return {"album_id": album_id, "moved": moved}
