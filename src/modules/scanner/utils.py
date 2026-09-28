"""Scanner utility functions for media import (v2 - storage abstraction)."""

import gc
import hashlib
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import aiomysql

from src.modules.catalog import metadata
from src.modules.catalog import service as catalog_service
from src.modules.storage.registry import get_default, get_default_name
from src.modules.tagger import service as tagger_service
from src.modules.thumbnails import service as thumbnail_service

logger = logging.getLogger(__name__)

# Max file size to load entirely in memory (200 MB)
MAX_FILE_BYTES = 200 * 1024 * 1024

# Default album ID for scanned imports (/originals)
DEFAULT_IMPORT_ALBUM_ID = 2


def calculate_file_hash(file_bytes: bytes) -> str:
    """Calculate SHA256 hash of file bytes.

    Args:
        file_bytes: File content.

    Returns:
        SHA256 hex digest.
    """
    return hashlib.sha256(file_bytes).hexdigest()


async def import_media_file(
    conn: aiomysql.Connection,
    file_bytes: bytes,
    source_id: int,
    source_path: str,
    title: str,
    mime_type: str,
    auto_tag: bool,
    extracted_metadata: dict[str, Any],
    file_hash: str | None = None,
    album_id: int = DEFAULT_IMPORT_ALBUM_ID,
) -> int:
    """Import a media file: upload to storage, catalog, generate thumbnail, suggest tags.

    Args:
        conn: Database connection.
        file_bytes: File content.
        source_id: Source ID.
        source_path: Path in source.
        title: Media title.
        mime_type: MIME type.
        auto_tag: Generate tag suggestions.
        extracted_metadata: Extracted metadata.
        file_hash: SHA256 hash for deduplication.
        album_id: Target album ID.

    Returns:
        Image ID (0 if skipped).
    """
    if len(file_bytes) > MAX_FILE_BYTES:
        logger.warning(
            f"Skipping oversized file {source_path} "
            f"({len(file_bytes) / 1024 / 1024:.0f} MB > {MAX_FILE_BYTES / 1024 / 1024:.0f} MB limit)"
        )
        return 0

    # Generate storage path
    if not file_hash:
        file_hash = calculate_file_hash(file_bytes)

    ext = Path(source_path).suffix or ".bin"
    now = datetime.now()
    storage_path = f"originals/{now.year}/{now.month:02d}/{file_hash[:12]}{ext}"

    # Upload to default storage backend
    backend = get_default()
    await backend.upload(file_bytes, storage_path)

    # Determine media type
    media_type = metadata.get_media_type(mime_type)

    # Create catalog entry
    image_id = await catalog_service.create_media(
        conn=conn,
        name=f"{file_hash[:12]}{ext}",
        title=title,
        description="",
        media_type=media_type,
        mime_type=mime_type,
        album_id=album_id,
        storage_backend=get_default_name(),
        storage_path=storage_path,
        file_size=len(file_bytes),
        metadata=extracted_metadata,
        source_id=source_id,
        source_path=source_path,
        tags=[],
        file_hash=file_hash,
    )

    # Generate thumbnail
    try:
        if media_type == "image":
            await thumbnail_service.generate_image_thumbnail(file_bytes, str(image_id))
        elif media_type == "video":
            with tempfile.NamedTemporaryFile(suffix=Path(source_path).suffix, delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            try:
                await thumbnail_service.generate_video_thumbnail(tmp_path, str(image_id))
            finally:
                Path(tmp_path).unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Thumbnail generation failed for {image_id}: {e}")

    # Suggest tags if enabled
    if auto_tag and media_type == "image":
        try:
            suggested = await tagger_service.suggest_tags(file_bytes, extracted_metadata)
            if suggested:
                await catalog_service.update_tags(conn, image_id, suggested)
        except Exception as e:
            logger.warning(f"Tag suggestion failed for {image_id}: {e}")

    del file_bytes
    gc.collect()

    return image_id
