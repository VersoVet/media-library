"""Scanner service for multi-source orchestration."""

import json
import logging
import mimetypes
import tempfile
from pathlib import Path
from typing import Any

import aiosqlite
import asyncssh

from src.models import SyncReport
from src.modules.catalog import metadata
from src.modules.catalog import service as catalog_service
from src.modules.dropbox import service as dropbox_service
from src.modules.sources import service as sources_service
from src.modules.tagger import service as tagger_service
from src.modules.thumbnails import service as thumbnail_service

logger = logging.getLogger(__name__)


async def scan_source(
    db: aiosqlite.Connection,
    source: dict[str, Any],
) -> SyncReport:
    """Scan a source and import new media.

    Args:
        db: Database connection.
        source: Source dict from database.

    Returns:
        Sync report with import statistics.
    """
    source_id = source["id"]
    source_type = source["source_type"]
    config = json.loads(source.get("config_json", "{}"))

    await sources_service.update_scan_status(db, source_id, "running")

    try:
        if source_type == "dropbox":
            report = await _scan_dropbox_source(db, source_id, config, source)
        elif source_type == "local":
            report = await _scan_local_source(db, source_id, config, source)
        elif source_type == "ssh":
            report = await _scan_ssh_source(db, source_id, config, source)
        else:
            raise ValueError(f"Unknown source type: {source_type}")

        await sources_service.update_scan_status(db, source_id, "ok")
        logger.info(f"Scan complete for source {source_id}: {report}")
        return report

    except Exception as e:
        logger.error(f"Scan failed for source {source_id}: {e}")
        await sources_service.update_scan_status(db, source_id, "error")
        raise


async def _scan_dropbox_source(
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

    # Filter for supported media files
    for entry in entries:
        if entry.get(".tag") != "file":
            continue

        files_found += 1
        file_path = entry.get("path_display", "")
        file_name = entry.get("name", "")

        try:
            # Check if already imported
            cursor = await db.execute(
                "SELECT id FROM media WHERE dropbox_path = ?",
                (file_path,),
            )
            if await cursor.fetchone():
                files_skipped += 1
                continue

            # Download file
            file_bytes = await dropbox_service.download_file(file_path)

            # Detect MIME type
            mime_type, _ = mimetypes.guess_type(file_name)
            if not mime_type:
                mime_type = "application/octet-stream"

            # Check if supported
            if not (metadata.is_supported_image(mime_type) or metadata.is_supported_video(mime_type)):
                files_skipped += 1
                continue

            # Extract metadata
            if metadata.is_supported_image(mime_type):
                extracted = metadata.extract_image_metadata(file_bytes)
            else:
                extracted = {}

            # Import media
            await _import_media_file(
                db=db,
                file_bytes=file_bytes,
                source_id=source_id,
                source_path=file_path,
                title=Path(file_name).stem,
                mime_type=mime_type,
                auto_tag=auto_tag,
                extracted_metadata=extracted,
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


async def _scan_local_source(
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

    # Find all media files
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
            # Detect MIME type
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if not mime_type:
                mime_type = "application/octet-stream"

            if not (metadata.is_supported_image(mime_type) or metadata.is_supported_video(mime_type)):
                files_skipped += 1
                continue

            # Check if already imported
            relative_path = str(file_path.relative_to(path))
            cursor = await db.execute(
                "SELECT id FROM media WHERE source_id = ? AND source_path = ?",
                (source_id, relative_path),
            )
            if await cursor.fetchone():
                files_skipped += 1
                continue

            # Read file
            file_bytes = file_path.read_bytes()

            # Extract metadata
            if metadata.is_supported_image(mime_type):
                extracted = metadata.extract_image_metadata(file_bytes)
            else:
                extracted = {}

            # Import media
            await _import_media_file(
                db=db,
                file_bytes=file_bytes,
                source_id=source_id,
                source_path=relative_path,
                title=file_path.stem,
                mime_type=mime_type,
                auto_tag=auto_tag,
                extracted_metadata=extracted,
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


async def _scan_ssh_source(
    db: aiosqlite.Connection,
    source_id: int,
    config: dict[str, Any],
    source_row: dict[str, Any],
) -> SyncReport:
    """Scan SSH source."""
    host = config.get("host")
    port = config.get("port", 22)
    user = config.get("user")
    key_name = config.get("key")
    path = config.get("path", "/")

    if not all([host, user, key_name]):
        raise ValueError("SSH config missing host, user, or key")

    # Get SSH key from Vault
    import os

    token = os.getenv("ONYX_VAULT_TOKEN", "")
    if not token:
        raise ValueError("ONYX_VAULT_TOKEN not set")

    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://10.0.0.44:8050/vault/{key_name}",
            headers={"X-Vault-Token": token},
            timeout=10.0,
        )
        response.raise_for_status()
        private_key = response.json().get("value", "")

    if not private_key:
        raise ValueError(f"SSH key not found in Vault: {key_name}")

    files_found = 0
    files_imported = 0
    files_skipped = 0
    errors: list[str] = []

    try:
        async with asyncssh.connect(
            host,
            port=port,
            username=user,
            client_keys=[asyncssh.import_private_key(private_key)],
            known_hosts=None,
        ) as conn:
            # List files remotely
            async with conn.open_sftp_client() as sftp:
                for entry in await sftp.listdir_attr(path):
                    if not entry.is_file():
                        continue

                    files_found += 1
                    file_name = entry.filename
                    remote_path = f"{path}/{file_name}".lstrip("/")

                    try:
                        # Detect MIME type
                        mime_type, _ = mimetypes.guess_type(file_name)
                        if not mime_type:
                            mime_type = "application/octet-stream"

                        if not (metadata.is_supported_image(mime_type) or metadata.is_supported_video(mime_type)):
                            files_skipped += 1
                            continue

                        # Check if already imported
                        cursor = await db.execute(
                            "SELECT id FROM media WHERE source_id = ? AND source_path = ?",
                            (source_id, remote_path),
                        )
                        if await cursor.fetchone():
                            files_skipped += 1
                            continue

                        # Download file via SFTP
                        with tempfile.NamedTemporaryFile(delete=False) as tmp:
                            tmp_path = tmp.name

                        await sftp.get(remote_path, tmp_path)
                        file_bytes = Path(tmp_path).read_bytes()
                        Path(tmp_path).unlink()

                        # Extract metadata
                        if metadata.is_supported_image(mime_type):
                            extracted = metadata.extract_image_metadata(file_bytes)
                        else:
                            extracted = {}

                        # Import media
                        await _import_media_file(
                            db=db,
                            file_bytes=file_bytes,
                            source_id=source_id,
                            source_path=remote_path,
                            title=Path(file_name).stem,
                            mime_type=mime_type,
                            auto_tag=False,  # SSH import doesn't auto-tag by default
                            extracted_metadata=extracted,
                        )

                        files_imported += 1

                    except Exception as e:
                        logger.error(f"Failed to import {remote_path}: {e}")
                        errors.append(f"{remote_path}: {str(e)}")

    except Exception as e:
        logger.error(f"SSH connection failed: {e}")
        errors.append(str(e))

    return SyncReport(
        source_id=source_id,
        files_found=files_found,
        files_imported=files_imported,
        files_skipped=files_skipped,
        errors=errors,
        duration_seconds=0.0,
    )


async def _import_media_file(
    db: aiosqlite.Connection,
    file_bytes: bytes,
    source_id: int,
    source_path: str,
    title: str,
    mime_type: str,
    auto_tag: bool,
    extracted_metadata: dict[str, Any],
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

    Returns:
        Media ID.
    """
    # Generate media ID and Dropbox path
    media_id = await catalog_service.generate_media_id()
    ext = Path(source_path).suffix or ".bin"
    dropbox_path = f"/media-library/{media_id}{ext}"

    # Upload to Dropbox
    await dropbox_service.upload_file(file_bytes, dropbox_path)

    # Determine media type
    media_type = metadata.get_media_type(mime_type)

    # Create catalog entry
    await catalog_service.create_media(
        db=db,
        title=title,
        description="",
        media_type=media_type,
        mime_type=mime_type,
        dropbox_path=dropbox_path,
        file_size=len(file_bytes),
        metadata=extracted_metadata,
        source_id=source_id,
        source_path=source_path,
        tags=[],
    )

    # Generate thumbnail
    try:
        if media_type == "image":
            await thumbnail_service.generate_image_thumbnail(file_bytes, media_id)
    except Exception as e:
        logger.warning(f"Thumbnail generation failed for {media_id}: {e}")

    # Suggest tags if enabled
    if auto_tag and media_type == "image":
        try:
            suggested = await tagger_service.suggest_tags(file_bytes, extracted_metadata)
            if suggested:
                await catalog_service.update_tags(db, media_id, suggested)
        except Exception as e:
            logger.warning(f"Tag suggestion failed for {media_id}: {e}")

    return media_id


async def scan_all_enabled_sources(db: aiosqlite.Connection) -> list[SyncReport]:
    """Scan all enabled sources.

    Args:
        db: Database connection.

    Returns:
        List of sync reports.
    """
    from src.modules.sources import service as sources_service

    sources = await sources_service.list_sources(db)
    reports = []

    for source_row in sources:
        if not source_row.get("enabled", False):
            continue

        try:
            report = await scan_source(db, source_row)
            reports.append(report)
        except Exception as e:
            logger.error(f"Scan failed for source {source_row['id']}: {e}")

    return reports
