"""Tagger API routes for tag suggestions."""

import logging

from aiosqlite import Connection
from fastapi import APIRouter, Depends, HTTPException

from src.database import get_db
from src.models import TagSuggestion
from src.modules.catalog import service as catalog_service

from . import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["tagger"])


@router.post("/media/{media_id}/suggest-tags", response_model=TagSuggestion)
async def suggest_tags(
    media_id: str,
    db: Connection = Depends(get_db),
) -> TagSuggestion:
    """Suggest tags for a media using LLM vision.

    Args:
        media_id: Media ID.
        db: Database connection.

    Returns:
        Suggested tags (not saved).

    Raises:
        HTTPException: If media not found or analysis fails.
    """
    # Get media
    media = await catalog_service.get_media(db, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    # Skip if not an image
    if media.get("media_type") != "image":
        raise HTTPException(status_code=400, detail="Tag suggestion only for images")

    # Download image from Dropbox
    from src.modules.dropbox import service as dropbox_service

    try:
        img_bytes = await dropbox_service.download_file(media["dropbox_path"])
    except Exception as e:
        logger.error(f"Failed to download media for tagging: {e}")
        raise HTTPException(status_code=500, detail="Failed to download media")

    # Get metadata for fallback
    import json

    metadata = json.loads(media.get("metadata_json", "{}"))

    # Suggest tags
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
    media_id: str,
    tags: list[str],
    db: Connection = Depends(get_db),
) -> dict[str, str]:
    """Apply suggested tags to a media.

    Args:
        media_id: Media ID.
        tags: Tags to apply.
        db: Database connection.

    Returns:
        Confirmation message.

    Raises:
        HTTPException: If media not found or operation fails.
    """
    try:
        # Verify media exists
        media = await catalog_service.get_media(db, media_id)
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")

        # Update tags
        await catalog_service.update_tags(db, media_id, tags)

        logger.info(f"Applied {len(tags)} tags to media {media_id}")
        return {"status": "tags_applied", "media_id": media_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Apply tags failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
