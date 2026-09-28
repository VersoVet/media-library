"""Thumbnail serving routes (storage-backend aware)."""

import logging
import tempfile
from pathlib import Path
from typing import Any

import aiomysql
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from src.database import get_db
from src.modules.catalog import service as catalog_service
from src.modules.storage.registry import get_backend

from . import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["thumbnails"])


@router.get("/media/{media_id}/thumbnail")
async def get_thumbnail(
    media_id: int,
    conn: aiomysql.Connection = Depends(get_db),
) -> FileResponse:
    """Get thumbnail for media.

    Generates thumbnail if not cached.

    Args:
        media_id: Media ID.
        conn: Database connection.

    Returns:
        Thumbnail file response (webp or gif).
    """
    media = await catalog_service.get_media(conn, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    from src.database import IMAGE_CATEGORY_IMAGE

    is_video = media.get("category") != IMAGE_CATEGORY_IMAGE
    thumb_path = service.get_thumbnail_path(str(media_id), is_video=is_video)
    if thumb_path.exists():
        content_type = "image/gif" if is_video else "image/webp"
        return FileResponse(path=thumb_path, media_type=content_type)

    # Generate thumbnail from storage backend
    try:
        backend_name = media.get("storage_backend", "nas")
        storage_path = media.get("storage_path", "")
        backend = get_backend(backend_name)

        if not is_video:
            img_bytes = await backend.download(storage_path)
            await service.generate_image_thumbnail(img_bytes, str(media_id))
        else:
            video_bytes = await backend.download(storage_path)
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                tmp.write(video_bytes)
                tmp_path = tmp.name
            try:
                await service.generate_video_thumbnail(tmp_path, str(media_id))
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        if thumb_path.exists():
            content_type = "image/gif" if is_video else "image/webp"
            return FileResponse(path=thumb_path, media_type=content_type)
        raise HTTPException(status_code=500, detail="Failed to generate thumbnail")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Thumbnail generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/regenerate-video-thumbnails")
async def regenerate_video_thumbnails(
    conn: aiomysql.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Regenerate GIF thumbnails for all video media.

    Args:
        conn: Database connection.

    Returns:
        Report with success/failure counts.
    """
    import asyncio

    from src.database import IMAGE_CATEGORY_VIDEO, IMAGE_STATUS_VISIBLE, fetchall

    try:
        videos = await fetchall(
            conn,
            "SELECT i.id FROM Images i WHERE i.category = %s AND i.status = %s",
            (IMAGE_CATEGORY_VIDEO, IMAGE_STATUS_VISIBLE),
        )

        success_count = 0
        failure_count = 0
        errors: list[str] = []

        for video in videos:
            video_id = video["id"]
            try:
                media = await catalog_service.get_media(conn, video_id)
                if not media:
                    continue

                backend_name = media.get("storage_backend", "nas")
                storage_path = media.get("storage_path", "")
                backend = get_backend(backend_name)

                video_bytes = await backend.download(storage_path)
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                    tmp.write(video_bytes)
                    tmp_path = tmp.name

                try:
                    result = await asyncio.wait_for(
                        service.generate_video_thumbnail(tmp_path, str(video_id)),
                        timeout=20.0,
                    )
                    if result:
                        success_count += 1
                    else:
                        failure_count += 1
                        errors.append(f"{video_id}: Generation failed")
                except TimeoutError:
                    failure_count += 1
                    errors.append(f"{video_id}: Timeout (>20s)")
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

            except Exception as e:
                failure_count += 1
                errors.append(f"{video_id}: {e}")

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
