"""Thumbnail serving routes."""

import logging
import tempfile
from pathlib import Path
from typing import Any

from aiosqlite import Connection
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from src.database import get_db
from src.modules.catalog import service as catalog_service
from src.modules.dropbox import service as dropbox_service

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
            # Download video and generate GIF thumbnail
            video_bytes = await dropbox_service.download_file(media["dropbox_path"])
            # Save to temp file
            with tempfile.NamedTemporaryFile(
                suffix=".mp4", delete=False
            ) as tmp:
                tmp.write(video_bytes)
                tmp_path = tmp.name
            try:
                await service.generate_video_thumbnail(tmp_path, media_id)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        # Return generated thumbnail
        if thumb_path.exists():
            # Determine media type based on file extension
            media_type = (
                "image/gif" if media.get("media_type") == "video" else "image/webp"
            )
            return FileResponse(path=thumb_path, media_type=media_type)
        else:
            raise HTTPException(status_code=500, detail="Failed to generate thumbnail")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Thumbnail generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/regenerate-video-thumbnails")
async def regenerate_video_thumbnails(
    db: Connection = Depends(get_db),
) -> dict[str, Any]:
    """Regenerate GIF thumbnails for all video media.

    Downloads each video from Dropbox and generates a lightweight GIF.

    Args:
        db: Database connection.

    Returns:
        Report with success/failure counts.

    Raises:
        HTTPException: If database operation fails.
    """
    try:
        # Get all videos
        cursor = await db.execute(
            "SELECT id, dropbox_path FROM media WHERE media_type = 'video'",
        )
        videos = await cursor.fetchall()

        success_count = 0
        failure_count = 0
        errors: list[str] = []

        for video in videos:
            video_id = dict(video)["id"]
            dropbox_path = dict(video)["dropbox_path"]

            try:
                logger.info(f"Regenerating GIF for video {video_id}")

                # Download video
                video_bytes = await dropbox_service.download_file(dropbox_path)

                # Save to temp file
                with tempfile.NamedTemporaryFile(
                    suffix=".mp4", delete=False
                ) as tmp:
                    tmp.write(video_bytes)
                    tmp_path = tmp.name

                try:
                    # Generate GIF with timeout protection
                    import asyncio
                    result = await asyncio.wait_for(
                        service.generate_video_thumbnail(tmp_path, video_id),
                        timeout=20.0,
                    )
                    if result:
                        success_count += 1
                        logger.info(f"✓ GIF generated for {video_id}")
                    else:
                        failure_count += 1
                        error_msg = f"{video_id}: Generation failed (None returned)"
                        errors.append(error_msg)
                        logger.warning(error_msg)
                except asyncio.TimeoutError:
                    failure_count += 1
                    error_msg = f"{video_id}: Timeout (>20s)"
                    errors.append(error_msg)
                    logger.error(error_msg)
                finally:
                    # Clean up temp file
                    Path(tmp_path).unlink(missing_ok=True)

            except Exception as e:
                failure_count += 1
                error_msg = f"{video_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"Failed to regenerate GIF for {video_id}: {e}")

        logger.info(
            f"GIF regeneration complete: {success_count} succeeded, "
            f"{failure_count} failed"
        )

        return {
            "status": "completed",
            "total": len(videos),
            "success": success_count,
            "failed": failure_count,
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"GIF regeneration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
