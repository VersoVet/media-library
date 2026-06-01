"""Dropbox source scanner."""

import logging
import mimetypes
from pathlib import Path
from typing import Any

import aiosqlite

from src.models import SyncReport
from src.modules.catalog import metadata
from src.modules.dropbox import service as dropbox_service
from src.modules.scanner import utils

logger = logging.getLogger(__name__)


async def scan_dropbox_source(
    db: aiosqlite.Connection,
    source_id: int,
    config: dict[str, Any],
    source_row: dict[str, Any],
) -> SyncReport:
    """Scan Dropbox source."""
    path = config.get("path", "/")
    recursive = bool(source_row.get("recursive", 1))
    auto_tag = bool(source_row.get("auto_tag", 1))

    entries = await dropbox_service.list_folder(path, recursive=recursive)

    files_found = 0
    files_imported = 0
    files_skipped = 0
    errors: list[str] = []

    for entry in entries:
        if entry.get(".tag") != "file":
            continue

        files_found += 1
        file_path = entry.get("path_display", "")
        file_name = entry.get("name", "")

        try:
            cursor = await db.execute(
                "SELECT id FROM media WHERE dropbox_path = ?",
                (file_path,),
            )
            if await cursor.fetchone():
                files_skipped += 1
                continue

            file_bytes = await dropbox_service.download_file(file_path)
            mime_type, _ = mimetypes.guess_type(file_name)
            if not mime_type:
                mime_type = "application/octet-stream"

            if not (metadata.is_supported_image(mime_type) or metadata.is_supported_video(mime_type)):
                files_skipped += 1
                continue

            file_hash = utils.calculate_file_hash(file_bytes)

            cursor = await db.execute(
                "SELECT id FROM media WHERE file_hash = ?",
                (file_hash,),
            )
            if await cursor.fetchone():
                files_skipped += 1
                logger.info(f"File already imported (hash match): {file_path}")
                continue

            extracted = metadata.extract_image_metadata(file_bytes) if metadata.is_supported_image(mime_type) else {}

            await utils.import_media_file(
                db=db,
                file_bytes=file_bytes,
                source_id=source_id,
                source_path=file_path,
                title=Path(file_name).stem,
                mime_type=mime_type,
                auto_tag=auto_tag,
                extracted_metadata=extracted,
                file_hash=file_hash,
            )

            files_imported += 1

        except Exception as e:
            logger.error(f"Failed to import {file_path}: {e}")
            errors.append(f"{file_path}: {str(e)}")
            continue

    return SyncReport(
        source_id=source_id,
        files_found=files_found,
        files_imported=files_imported,
        files_skipped=files_skipped,
        errors=errors,
        duration_seconds=0.0,
    )
