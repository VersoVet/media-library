"""Scanner utility functions for media import."""

import gc
import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Any

import aiosqlite

from src.modules.catalog import metadata
from src.modules.catalog import service as catalog_service
from src.modules.dropbox import service as dropbox_service
from src.modules.tagger import service as tagger_service
from src.modules.thumbnails import service as thumbnail_service

logger = logging.getLogger(__name__)

# Max file size to load entirely in memory (200 MB)
MAX_FILE_BYTES = 200 * 1024 * 1024


def calculate_file_hash(file_bytes: bytes) -> str:
    """Calculate SHA256 hash of file bytes.

    Args:
        file_bytes: File content.

    Returns:
        SHA256 hex digest.
    """
    return hashlib.sha256(file_bytes).hexdigest()


async def import_media_file(
    db: aiosqlite.Connection,
    file_bytes: bytes,
    source_id: int,
    source_path: str,
    title: str,
    mime_type: str,
    auto_tag: bool,
    extracted_metadata: dict[str, Any],
    file_hash: str | None = None,
) -> str:
    """Import a media file: upload to Dropbox, catalog, generate thumbnail, suggest tags.

    Args:
        db: Database connection.
        file_bytes: File content.
        source_id: Source ID.
        source_path: Path in source.
        title: Media title.
        mime_type: MIME type.
        auto_tag: Generate tag suggestions.
        extracted_metadata: Extracted metadata.
        file_hash: SHA256 hash for deduplication.

    Returns:
        Media ID.
    """
    # Reject oversized files to prevent memory explosion
    if len(file_bytes) > MAX_FILE_BYTES:
        logger.warning(
            f"Skipping oversized file {source_path} "
            f"({len(file_bytes) / 1024 / 1024:.0f} MB > {MAX_FILE_BYTES / 1024 / 1024:.0f} MB limit)"
        )
        return ""

    # Generate media ID and Dropbox path
    media_id = await catalog_service.generate_media_id()
    ext = Path(source_path).suffix or ".bin"
    dropbox_path = f"/media-library/{media_id}{ext}"

    # Upload to Dropbox
    await dropbox_service.upload_file(file_bytes, dropbox_path)

    # Determine media type
    media_type = metadata.get_media_type(mime_type)
    file_size = len(file_bytes)

    # Create catalog entry
    if not file_hash:
        file_hash = calculate_file_hash(file_bytes)

    await catalog_service.create_media(
        db=db,
        title=title,
        description="",
        media_type=media_type,
        mime_type=mime_type,
        dropbox_path=dropbox_path,
        file_size=file_size,
        metadata=extracted_metadata,
        source_id=source_id,
        source_path=source_path,
        tags=[],
        file_hash=file_hash,
    )

    # Generate thumbnail
    try:
        if media_type == "image":
            await thumbnail_service.generate_image_thumbnail(file_bytes, media_id)
        elif media_type == "video":
            # For videos, save temporarily then generate thumbnail
            with tempfile.NamedTemporaryFile(suffix=Path(source_path).suffix, delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            try:
                await thumbnail_service.generate_video_thumbnail(tmp_path, media_id)
            finally:
                Path(tmp_path).unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Thumbnail generation failed for {media_id}: {e}")

    # Suggest tags if enabled (images only - vision API limitation)
    if auto_tag and media_type == "image":
        try:
            suggested = await tagger_service.suggest_tags(file_bytes, extracted_metadata)
            if suggested:
                await catalog_service.update_tags(db, media_id, suggested)
        except Exception as e:
            logger.warning(f"Tag suggestion failed for {media_id}: {e}")

    # Explicit cleanup of large bytes buffer
    del file_bytes
    gc.collect()

    return media_id
