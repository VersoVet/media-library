"""Dropbox API integration service."""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def get_secret(key: str) -> str:
    """Retrieve secret from OnyxVault.

    Args:
        key: Secret key name.

    Returns:
        Secret value.

    Raises:
        ValueError: If Vault is unreachable or key not found.
    """
    token = os.getenv("ONYX_VAULT_TOKEN", "")
    if not token:
        raise ValueError("ONYX_VAULT_TOKEN not set")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://10.0.0.44:8050/vault/{key}",
            headers={"X-Vault-Token": token},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json().get("value", "")


async def get_dropbox_token() -> str:
    """Get Dropbox access token from Vault.

    Returns:
        Dropbox token.

    Raises:
        ValueError: If token not available.
    """
    return await get_secret("dropbox_token")


async def list_folder(path: str, recursive: bool = False) -> list[dict[str, Any]]:
    """List files in Dropbox folder.

    Args:
        path: Dropbox folder path.
        recursive: Include subfolders.

    Returns:
        List of file entries.

    Raises:
        Exception: If API call fails.
    """
    token = await get_dropbox_token()
    entries: list[dict[str, Any]] = []

    async with httpx.AsyncClient() as client:
        cursor = None
        while True:
            if cursor:
                # Continuation of previous list
                payload = {"cursor": cursor}
                endpoint = "https://api.dropboxapi.com/2/files/list_folder/continue"
            else:
                # Initial request
                payload = {"path": path, "recursive": recursive}
                endpoint = "https://api.dropboxapi.com/2/files/list_folder"

            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            entries.extend(data.get("entries", []))

            if not data.get("has_more", False):
                break

            cursor = data.get("cursor")

    logger.info(f"Listed {len(entries)} entries from {path}")
    return entries


async def download_file(dropbox_path: str) -> bytes:
    """Download file from Dropbox.

    Args:
        dropbox_path: Path to file in Dropbox.

    Returns:
        File bytes.

    Raises:
        Exception: If download fails.
    """
    import json

    token = await get_dropbox_token()

    # Try Dropbox API first (recommended)
    try:
        async with httpx.AsyncClient() as client:
            # Use json.dumps() to properly encode paths with non-ASCII characters
            dropbox_arg = json.dumps({"path": dropbox_path})
            response = await client.post(
                "https://content.dropboxapi.com/2/files/download",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Dropbox-API-Arg": dropbox_arg,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            logger.info(f"Downloaded {dropbox_path} ({len(response.content)} bytes)")
            return response.content
    except Exception as e:
        logger.error(f"Dropbox download failed for {dropbox_path}: {e}")
        raise


async def upload_file(file_bytes: bytes, dest_path: str) -> dict[str, Any]:
    """Upload file to Dropbox.

    Args:
        file_bytes: File content.
        dest_path: Destination path in Dropbox.

    Returns:
        Dropbox file metadata.

    Raises:
        Exception: If upload fails.
    """
    import json

    token = await get_dropbox_token()

    async with httpx.AsyncClient() as client:
        # Use json.dumps() to properly encode paths with non-ASCII characters
        dropbox_arg = json.dumps({"path": dest_path, "mode": "add"})
        response = await client.post(
            "https://content.dropboxapi.com/2/files/upload",
            headers={
                "Authorization": f"Bearer {token}",
                "Dropbox-API-Arg": dropbox_arg,
                "Content-Type": "application/octet-stream",
            },
            content=file_bytes,
            timeout=60.0,
        )
        response.raise_for_status()
        metadata = response.json()
        logger.info(f"Uploaded to {dest_path} ({metadata.get('size')} bytes)")
        return metadata


async def get_temp_link(dropbox_path: str) -> str:
    """Get temporary download link for a file.

    Args:
        dropbox_path: Path to file in Dropbox.

    Returns:
        Temporary URL (valid for 4 hours).

    Raises:
        Exception: If request fails.
    """
    token = await get_dropbox_token()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.dropboxapi.com/2/files/get_temporary_link",
            headers={"Authorization": f"Bearer {token}"},
            json={"path": dropbox_path},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        link = data.get("link", "")
        logger.info(f"Generated temp link for {dropbox_path}")
        return link


async def file_exists(dropbox_path: str) -> bool:
    """Check if file exists in Dropbox.

    Args:
        dropbox_path: Path to check.

    Returns:
        True if file exists.
    """
    token = await get_dropbox_token()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.dropboxapi.com/2/files/get_metadata",
            headers={"Authorization": f"Bearer {token}"},
            json={"path": dropbox_path},
            timeout=10.0,
        )
        return response.status_code == 200
