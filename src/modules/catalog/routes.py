"""Catalog API routes (Digikam-compatible)."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiomysql
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile

from src.database import get_db
from src.models import MediaItem, UploadResponse
from src.modules.storage.registry import get_default, get_default_name

from . import metadata, service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["catalog"])

# Default album ID for uploads (originals)
DEFAULT_ALBUM_ID = 2  # /originals


def _row_to_media_item(row: dict[str, Any]) -> MediaItem:
    """Convert database row to MediaItem model.

    Args:
        row: Database row dict.

    Returns:
        MediaItem instance.
    """
    from src.database import IMAGE_CATEGORY_IMAGE

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
        orientation=row.get("orientation"),
        format=row.get("format"),
        tags=row.get("tags", []),
        created_at=row.get("creationDate"),
        updated_at=row.get("modificationDate"),
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_media(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(default=""),
    tags: str = Form(default=""),
    album_id: int = Form(default=DEFAULT_ALBUM_ID),
    conn: aiomysql.Connection = Depends(get_db),
) -> UploadResponse:
    """Upload a media file to storage and catalog it.

    Args:
        file: Media file (image or video).
        title: Media title.
        description: Media description.
        tags: Comma-separated tags.
        album_id: Target album ID.
        conn: Database connection.

    Returns:
        Upload response with media ID and metadata.
    """
    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Empty file")

        mime_type = file.content_type or "application/octet-stream"
        media_type = metadata.get_media_type(mime_type)

        if media_type == "image":
            if not metadata.is_supported_image(mime_type):
                raise HTTPException(status_code=400, detail=f"Unsupported: {mime_type}")
            extracted = metadata.extract_image_metadata(file_bytes)
        elif media_type == "video":
            if not metadata.is_supported_video(mime_type):
                raise HTTPException(status_code=400, detail=f"Unsupported: {mime_type}")
            extracted = {}
        else:
            raise HTTPException(status_code=400, detail="Unsupported media type")

        file_hash = service.calculate_file_hash(file_bytes)
        ext = Path(file.filename).suffix if file.filename else f".{mime_type.split('/')[-1]}"
        now = datetime.now()
        storage_path = f"originals/{now.year}/{now.month:02d}/{file_hash[:12]}{ext}"

        backend = get_default()
        await backend.upload(file_bytes, storage_path)

        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

        image_id = await service.create_media(
            conn=conn,
            name=f"{file_hash[:12]}{ext}",
            title=title,
            description=description,
            media_type=media_type,
            mime_type=mime_type,
            album_id=album_id,
            storage_backend=get_default_name(),
            storage_path=storage_path,
            file_size=len(file_bytes),
            metadata=extracted,
            tags=tag_list,
            file_hash=file_hash,
        )

        return UploadResponse(
            id=image_id,
            title=title,
            storage_path=storage_path,
            storage_backend=get_default_name(),
            file_size=len(file_bytes),
            media_type=media_type,
            created_at=now,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/media/{image_id}")
async def get_media(
    image_id: int,
    conn: aiomysql.Connection = Depends(get_db),
) -> MediaItem:
    """Get media details by ID.

    Args:
        image_id: Media ID.
        conn: Database connection.

    Returns:
        Media item with metadata and tags.
    """
    media = await service.get_media(conn, image_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return _row_to_media_item(media)


@router.delete("/media/{image_id}")
async def delete_media(
    image_id: int,
    conn: aiomysql.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Delete media by ID.

    Args:
        image_id: Media ID.
        conn: Database connection.

    Returns:
        Success message.
    """
    deleted = await service.delete_media(conn, image_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Media not found")
    return {"status": "deleted", "id": image_id}


@router.put("/media/{image_id}/tags")
async def update_media_tags(
    image_id: int,
    tags: list[str] = Body(...),
    conn: aiomysql.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Update tags for a media.

    Args:
        image_id: Media ID.
        tags: New list of tags.
        conn: Database connection.

    Returns:
        Updated media tags.
    """
    try:
        await service.update_tags(conn, image_id, tags)
        return {"id": image_id, "tags": tags}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
