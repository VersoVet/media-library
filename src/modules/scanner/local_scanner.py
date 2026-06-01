"""Local filesystem source scanner."""

import logging
import mimetypes
from pathlib import Path
from typing import Any

import aiosqlite

from src.models import SyncReport
from src.modules.catalog import metadata
from src.modules.scanner import utils

logger = logging.getLogger(__name__)


async def scan_local_source(
    db: aiosqlite.Connection,
    source_id: int,
    config: dict[str, Any],
    source_row: dict[str, Any],
) -> SyncReport:
    """Scan local filesystem source."""
    path_str = config.get("path", ".")
    path = Path(path_str)

    if not path.exists():
        raise ValueError(f"Local path does not exist: {path_str}")

    recursive = bool(source_row.get("recursive", 1))
    auto_tag = bool(source_row.get("auto_tag", 1))

    pattern = "**/*" if recursive else "*"
    files_found = 0
    files_imported = 0
    files_skipped = 0
    errors: list[str] = []

    for file_path in path.glob(pattern):
        if not file_path.is_file():
            continue

        files_found += 1

        try:
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if not mime_type:
                mime_type = "application/octet-stream"

            if not (metadata.is_supported_image(mime_type) or metadata.is_supported_video(mime_type)):
                files_skipped += 1
                continue

            relative_path = str(file_path.relative_to(path))
            cursor = await db.execute(
                "SELECT id FROM media WHERE source_id = ? AND source_path = ?",
                (source_id, relative_path),
            )
            if await cursor.fetchone():
                files_skipped += 1
                continue

            file_bytes = file_path.read_bytes()
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
                source_path=relative_path,
                title=file_path.stem,
                mime_type=mime_type,
                auto_tag=auto_tag,
                extracted_metadata=extracted,
                file_hash=file_hash,
            )

            files_imported += 1

        except Exception as e:
            logger.error(f"Failed to import {file_path}: {e}")
            errors.append(f"{file_path}: {str(e)}")

    return SyncReport(
        source_id=source_id,
        files_found=files_found,
        files_imported=files_imported,
        files_skipped=files_skipped,
        errors=errors,
        duration_seconds=0.0,
    )
