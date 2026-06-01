"""SSH/SFTP remote source scanner."""

import logging
import mimetypes
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

import aiosqlite
import asyncssh
import httpx

from src.models import SyncReport
from src.modules.catalog import metadata
from src.modules.scanner import utils

logger = logging.getLogger(__name__)


async def scan_ssh_source(
    db: aiosqlite.Connection,
    source_id: int,
    config: dict[str, Any],
    source_row: dict[str, Any],
) -> SyncReport:
    """Scan SSH source."""
    host = config.get("host")
    port = config.get("port", 22)
    user = config.get("user")
    path = config.get("path", "/")

    if not all([host, user]):
        raise ValueError("SSH config missing host or user")

    key_name = config.get("key")
    password_key = config.get("password_key")

    client_keys = None
    password = None

    if key_name:
        token = os.getenv("ONYX_VAULT_TOKEN", "")
        if not token:
            raise ValueError("ONYX_VAULT_TOKEN not set")

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

        client_keys = [asyncssh.import_private_key(private_key)]

    elif password_key:
        token = os.getenv("ONYX_VAULT_TOKEN", "")
        if not token:
            raise ValueError("ONYX_VAULT_TOKEN not set")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://10.0.0.44:8050/vault/{password_key}",
                headers={"X-Vault-Token": token},
                timeout=10.0,
            )
            response.raise_for_status()
            password = response.json().get("value", "")

        if not password:
            raise ValueError(f"SSH password not found in Vault: {password_key}")
    else:
        raise ValueError("SSH config must have either 'key' or 'password_key'")

    recursive = bool(source_row.get("recursive", 1))
    auto_tag = bool(source_row.get("auto_tag", 1))

    files_found = 0
    files_imported = 0
    files_skipped = 0
    errors: list[str] = []

    async def walk_path(sftp: Any, current_path: str) -> None:
        """Recursively walk directory on SSH server."""
        nonlocal files_found, files_imported, files_skipped, errors

        logger.info(f"Walking SSH path: {current_path}")
        try:
            entries = await sftp.listdir(current_path)
            logger.info(f"Found {len(entries)} entries in {current_path}")
        except Exception as e:
            logger.warning(f"Failed to list {current_path}: {e}")
            return

        for entry in entries:
            try:
                file_name = entry.filename if hasattr(entry, "filename") else str(entry)

                if file_name in (".", ".."):
                    continue

                entry_path = (
                    f"{current_path}/{file_name}" if not current_path.endswith("/") else f"{current_path}{file_name}"
                )

                try:
                    attrs = await sftp.stat(entry_path)
                except FileNotFoundError:
                    logger.warning(f"Path not found: {entry_path}")
                    continue
                except Exception as e:
                    logger.warning(f"Failed to stat {entry_path}: {e}")
                    continue

                try:
                    mode = attrs.st_mode if hasattr(attrs, "st_mode") else attrs.permissions
                    if stat.S_ISDIR(mode):
                        if recursive:
                            await walk_path(sftp, entry_path)
                        continue
                    if not stat.S_ISREG(mode):
                        continue
                except Exception as e:
                    logger.debug(f"Could not determine file type for {file_name}: {e}")
                    continue

                files_found += 1
                remote_path = entry_path
                logger.info(f"Processing file: {remote_path}")

                try:
                    mime_type, _ = mimetypes.guess_type(file_name)
                    if not mime_type:
                        mime_type = "application/octet-stream"

                    if not (metadata.is_supported_image(mime_type) or metadata.is_supported_video(mime_type)):
                        files_skipped += 1
                        continue

                    cursor = await db.execute(
                        "SELECT id FROM media WHERE source_id = ? AND source_path = ?",
                        (source_id, remote_path),
                    )
                    if await cursor.fetchone():
                        files_skipped += 1
                        continue

                    with tempfile.NamedTemporaryFile(delete=False) as tmp:
                        tmp_path = tmp.name

                    await sftp.get(remote_path, tmp_path)
                    file_bytes = Path(tmp_path).read_bytes()
                    Path(tmp_path).unlink()

                    file_hash = utils.calculate_file_hash(file_bytes)

                    cursor = await db.execute(
                        "SELECT id FROM media WHERE file_hash = ?",
                        (file_hash,),
                    )
                    if await cursor.fetchone():
                        files_skipped += 1
                        logger.info(f"File already imported (hash match): {remote_path}")
                        continue

                    extracted = (
                        metadata.extract_image_metadata(file_bytes) if metadata.is_supported_image(mime_type) else {}
                    )

                    await utils.import_media_file(
                        db=db,
                        file_bytes=file_bytes,
                        source_id=source_id,
                        source_path=remote_path,
                        title=Path(file_name).stem,
                        mime_type=mime_type,
                        auto_tag=auto_tag,
                        extracted_metadata=extracted,
                        file_hash=file_hash,
                    )

                    files_imported += 1

                except Exception as e:
                    logger.error(f"Failed to import {remote_path}: {e}")
                    errors.append(f"{remote_path}: {str(e)}")
            except Exception as e:
                logger.error(f"Error processing entry {file_name}: {e}")

    try:
        logger.info(f"Connecting to SSH {user}@{host}:{port}")
        async with asyncssh.connect(
            host,
            port=port,
            username=user,
            client_keys=client_keys,
            password=password,
            known_hosts=None,
        ) as conn:
            logger.info("SSH connection established")
            async with await conn.start_sftp_client() as sftp:
                logger.info("SFTP client started")
                await walk_path(sftp, path)

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
