"""Tagger API routes for tag suggestions."""

import logging

import aiomysql
from fastapi import APIRouter, Depends, HTTPException

from src.database import get_db
from src.models import TagSuggestion
from src.modules.catalog import service as catalog_service
from src.modules.storage.registry import get_backend

from . import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["tagger"])


@router.post("/media/{media_id}/suggest-tags", response_model=TagSuggestion)
async def suggest_tags(
    media_id: int,
    conn: aiomysql.Connection = Depends(get_db),
) -> TagSuggestion:
    """Suggest tags for a media using LLM vision.

    Args:
        media_id: Media ID.
        conn: Database connection.

    Returns:
        Suggested tags (not saved).
    """
    media = await catalog_service.get_media(conn, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    from src.database import IMAGE_CATEGORY_IMAGE

    if media.get("category") != IMAGE_CATEGORY_IMAGE:
        raise HTTPException(status_code=400, detail="Tag suggestion only for images")

    # Download image from storage backend
    backend_name = media.get("storage_backend", "nas")
    storage_path = media.get("storage_path", "")

    try:
        backend = get_backend(backend_name)
        img_bytes = await backend.download(storage_path)
    except Exception as e:
        logger.error(f"Failed to download media for tagging: {e}")
        raise HTTPException(status_code=500, detail="Failed to download media")

    metadata: dict = {}

    try:
        suggested = await service.suggest_tags(img_bytes, metadata)
    except Exception as e:
        logger.error(f"Tag suggestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return TagSuggestion(
        media_id=media_id,
        suggested_tags=suggested,
        confidence=None,
    )


@router.post("/media/{media_id}/apply-tags")
async def apply_suggested_tags(
    media_id: int,
    tags: list[str],
    conn: aiomysql.Connection = Depends(get_db),
) -> dict[str, str]:
    """Apply suggested tags to a media.

    Args:
        media_id: Media ID.
        tags: Tags to apply.
        conn: Database connection.

    Returns:
        Confirmation message.
    """
    try:
        media = await catalog_service.get_media(conn, media_id)
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")

        await catalog_service.update_tags(conn, media_id, tags)

        logger.info(f"Applied {len(tags)} tags to media {media_id}")
        return {"status": "tags_applied", "media_id": str(media_id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Apply tags failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
