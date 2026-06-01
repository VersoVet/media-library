"""Catalog API routes."""

import logging
from datetime import datetime
from typing import Any

from aiosqlite import Connection
from fastapi import APIRouter, File, Form, UploadFile, Depends, HTTPException

from src.database import get_db
from src.models import MediaItem, UploadResponse, MediaMetadata
from . import metadata, service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["catalog"])


def _row_to_media_item(row: dict[str, Any]) -> MediaItem:
    """Convert database row to MediaItem model."""
    import json
    from datetime import datetime

    return MediaItem(
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
            exif=json.loads(row.get("metadata_json", "{}")).get("exif", {}),
        ),
        tags=row.get("tags", []),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_media(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(default=""),
    tags: str = Form(default=""),
    db: Connection = Depends(get_db),
) -> UploadResponse:
    """Upload a media file to Dropbox and catalog it.

    Args:
        file: Media file (image or video).
        title: Media title.
        description: Media description.
        tags: Comma-separated tags.
        db: Database connection.

    Returns:
        Upload response with media ID and metadata.

    Raises:
        HTTPException: If upload or cataloging fails.
    """
    try:
        # Read file
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Empty file")

        # Determine media type and extract metadata
        mime_type = file.content_type or "application/octet-stream"
        media_type = metadata.get_media_type(mime_type)

        if media_type == "image":
            if not metadata.is_supported_image(mime_type):
                raise HTTPException(status_code=400, detail=f"Unsupported image format: {mime_type}")
            extracted = metadata.extract_image_metadata(file_bytes)
        elif media_type == "video":
            if not metadata.is_supported_video(mime_type):
                raise HTTPException(status_code=400, detail=f"Unsupported video format: {mime_type}")
            # For video, we'd need to save and probe, but for now skip detailed metadata
            extracted = {}
        else:
            raise HTTPException(status_code=400, detail="Unsupported media type")

        # Prepare Dropbox path
        from src.modules.dropbox import service as dropbox_service
        media_id = await service.generate_media_id()
        ext = file.filename.split(".")[-1] if file.filename else media_type[0]
        dropbox_path = f"/media-library/{media_id}.{ext}"

        # Upload to Dropbox
        await dropbox_service.upload_file(file_bytes, dropbox_path)

        # Parse tags
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

        # Create database entry
        media_id = await service.create_media(
            db=db,
            title=title,
            description=description,
            media_type=media_type,
            mime_type=mime_type,
            dropbox_path=dropbox_path,
            file_size=len(file_bytes),
            metadata=extracted,
            tags=tag_list,
        )

        logger.info(f"Uploaded media {media_id}")

        return UploadResponse(
            id=media_id,
            title=title,
            dropbox_path=dropbox_path,
            file_size=len(file_bytes),
            media_type=media_type,
            created_at=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/media/{media_id}", response_model=MediaItem)
async def get_media(
    media_id: str,
    db: Connection = Depends(get_db),
) -> MediaItem:
    """Get media details by ID.

    Args:
        media_id: Media ID.
        db: Database connection.

    Returns:
        Media item with metadata and tags.

    Raises:
        HTTPException: If media not found.
    """
    media = await service.get_media(db, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    return _row_to_media_item(media)


@router.delete("/media/{media_id}")
async def delete_media(
    media_id: str,
    db: Connection = Depends(get_db),
) -> dict[str, str]:
    """Delete media by ID.

    Args:
        media_id: Media ID.
        db: Database connection.

    Returns:
        Success message.

    Raises:
        HTTPException: If media not found.
    """
    deleted = await service.delete_media(db, media_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Media not found")

    logger.info(f"Deleted media {media_id}")
    return {"status": "deleted", "id": media_id}


@router.put("/media/{media_id}/tags")
async def update_media_tags(
    media_id: str,
    tags: list[str],
    db: Connection = Depends(get_db),
) -> dict[str, Any]:
    """Update tags for a media.

    Args:
        media_id: Media ID.
        tags: New list of tags.
        db: Database connection.

    Returns:
        Updated media tags.

    Raises:
        HTTPException: If media not found.
    """
    try:
        await service.update_tags(db, media_id, tags)
        return {"id": media_id, "tags": tags}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Update tags failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
