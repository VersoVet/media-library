"""Dropbox storage backend implementation.

Wraps the existing dropbox/service.py module to conform
to the StorageBackend protocol.
"""

import logging
from typing import Any

from src.modules.dropbox import service as dropbox_service

logger = logging.getLogger(__name__)


class DropboxStorage:
    """Dropbox cloud storage backend.

    Uses the Dropbox API via the existing service module.
    URLs are temporary Dropbox download links (valid ~4 hours).
    """

    name: str = "dropbox"

    def __init__(self, base_path: str = "/media-library") -> None:
        """Initialize Dropbox storage.

        Args:
            base_path: Root folder in Dropbox (e.g., /media-library).
        """
        self.base_path = base_path

    def _dropbox_path(self, path: str) -> str:
        """Build full Dropbox path.

        Args:
            path: Relative path within the backend.

        Returns:
            Full Dropbox path.
        """
        return f"{self.base_path}/{path}".replace("//", "/")

    async def upload(self, file_bytes: bytes, dest_path: str) -> dict[str, Any]:
        """Upload file to Dropbox.

        Args:
            file_bytes: File content.
            dest_path: Relative path (e.g., originals/2026/09/abc.jpg).

        Returns:
            Metadata with path and size.
        """
        dbx_path = self._dropbox_path(dest_path)
        await dropbox_service.upload_file(file_bytes, dbx_path)
        return {"path": dest_path, "dropbox_path": dbx_path, "size": len(file_bytes), "backend": "dropbox"}

    async def download(self, path: str) -> bytes:
        """Download file from Dropbox.

        Args:
            path: Relative path within storage.

        Returns:
            File bytes.
        """
        dbx_path = self._dropbox_path(path)
        return await dropbox_service.download_file(dbx_path)

    async def get_url(self, path: str) -> str:
        """Get temporary download URL from Dropbox.

        Args:
            path: Relative path within storage.

        Returns:
            Temporary Dropbox URL (valid ~4 hours).
        """
        dbx_path = self._dropbox_path(path)
        return await dropbox_service.get_temp_link(dbx_path)

    async def exists(self, path: str) -> bool:
        """Check if file exists in Dropbox.

        Args:
            path: Relative path within storage.

        Returns:
            True if file exists.
        """
        dbx_path = self._dropbox_path(path)
        return await dropbox_service.file_exists(dbx_path)

    async def delete(self, path: str) -> bool:
        """Delete file from Dropbox.

        Args:
            path: Relative path within storage.

        Returns:
            True if deleted.
        """
        dbx_path = self._dropbox_path(path)
        token = await dropbox_service.get_dropbox_token()
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.dropboxapi.com/2/files/delete_v2",
                headers={"Authorization": f"Bearer {token}"},
                json={"path": dbx_path},
                timeout=30.0,
            )
            if response.status_code == 200:
                logger.info(f"Dropbox: deleted {dbx_path}")
                return True
            return False
