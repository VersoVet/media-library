"""Thumbnail serving routes."""

import logging

from aiosqlite import Connection
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from src.database import get_db
from src.modules.catalog import service as catalog_service

from . import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["thumbnails"])


@router.get("/media/{media_id}/thumbnail")
async def get_thumbnail(
    media_id: str,
    db: Connection = Depends(get_db),
) -> FileResponse:
    """Get thumbnail for media.

    Generates thumbnail if not cached.

    Args:
        media_id: Media ID.
        db: Database connection.

    Returns:
        Thumbnail file response (webp).

    Raises:
        HTTPException: If media not found or thumbnail generation fails.
    """
    # Get media
    media = await catalog_service.get_media(db, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    # Check if thumbnail exists
    thumb_path = service.get_thumbnail_path(media_id)
    if thumb_path.exists():
        return FileResponse(path=thumb_path, media_type="image/webp")

    # Generate thumbnail
    try:
        from src.modules.dropbox import service as dropbox_service

        if media.get("media_type") == "image":
            # Download image and generate thumbnail
            img_bytes = await dropbox_service.download_file(media["dropbox_path"])
            await service.generate_image_thumbnail(img_bytes, media_id)

        elif media.get("media_type") == "video":
            # For video, we'd need to download and extract frame
            # For now, just try to generate (requires ffmpeg)
            logger.warning(f"Video thumbnail generation not fully implemented for {media_id}")
            raise HTTPException(status_code=501, detail="Video thumbnails not yet implemented")

        # Return generated thumbnail
        if thumb_path.exists():
            return FileResponse(path=thumb_path, media_type="image/webp")
        else:
            raise HTTPException(status_code=500, detail="Failed to generate thumbnail")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Thumbnail generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
