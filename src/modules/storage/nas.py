"""NAS storage backend implementation.

Stores files on a local NFS/SMB-mounted NAS filesystem.
Serves files via FastAPI streaming endpoint.
"""

import logging
from pathlib import Path
from typing import Any

import aiofiles

from src.config import load_config

logger = logging.getLogger(__name__)


class NASStorage:
    """NAS filesystem storage backend.

    Files are stored on NFS-mounted NAS at the configured mount path.
    URLs point to the media-library API file-serving endpoint.
    """

    name: str = "nas"

    def __init__(self, mount_path: str, base_dir: str) -> None:
        """Initialize NAS storage.

        Args:
            mount_path: NFS mount point (e.g., /mnt/ml-store).
            base_dir: Subdirectory within mount (e.g., media-library).
        """
        self.mount_path = Path(mount_path)
        self.base_dir = base_dir
        self.root = self.mount_path / base_dir

    def _full_path(self, path: str) -> Path:
        """Resolve full filesystem path with traversal protection.

        Args:
            path: Relative path within the backend.

        Returns:
            Resolved absolute path.

        Raises:
            ValueError: If path attempts directory traversal.
        """
        full = (self.root / path).resolve()
        if not str(full).startswith(str(self.root.resolve())):
            raise ValueError(f"Path traversal detected: {path}")
        return full

    async def upload(self, file_bytes: bytes, dest_path: str) -> dict[str, Any]:
        """Upload file to NAS.

        Args:
            file_bytes: File content.
            dest_path: Relative path (e.g., originals/2026/09/abc.jpg).

        Returns:
            Metadata with path and size.
        """
        full = self._full_path(dest_path)
        full.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(full, "wb") as f:
            await f.write(file_bytes)

        logger.info(f"NAS: uploaded {dest_path} ({len(file_bytes)} bytes)")
        return {"path": dest_path, "size": len(file_bytes), "backend": "nas"}

    async def download(self, path: str) -> bytes:
        """Download file from NAS.

        Args:
            path: Relative path within NAS storage.

        Returns:
            File bytes.

        Raises:
            FileNotFoundError: If file does not exist.
        """
        full = self._full_path(path)
        if not full.exists():
            raise FileNotFoundError(f"NAS file not found: {path}")

        async with aiofiles.open(full, "rb") as f:
            data = await f.read()

        return data

    async def get_url(self, path: str) -> str:
        """Get API URL for serving the file.

        Args:
            path: Relative path within NAS storage.

        Returns:
            URL to the file-serving endpoint.
        """
        cfg = load_config()
        host = cfg.get("settings", {}).get("service_host", "10.0.0.21")
        port = cfg.get("settings", {}).get("service_port", 8202)
        return f"http://{host}:{port}/api/files/{path}"

    async def exists(self, path: str) -> bool:
        """Check if file exists on NAS.

        Args:
            path: Relative path within NAS storage.

        Returns:
            True if file exists.
        """
        return self._full_path(path).exists()

    async def delete(self, path: str) -> bool:
        """Delete file from NAS.

        Args:
            path: Relative path within NAS storage.

        Returns:
            True if deleted, False if not found.
        """
        full = self._full_path(path)
        if not full.exists():
            return False
        full.unlink()
        logger.info(f"NAS: deleted {path}")
        return True

    def get_full_path(self, path: str) -> Path:
        """Get the full filesystem path for a file.

        Args:
            path: Relative path within NAS storage.

        Returns:
            Absolute filesystem path.
        """
        return self._full_path(path)

    def is_mounted(self) -> bool:
        """Check if the NAS mount point is accessible.

        Returns:
            True if mount point exists and is a directory.
        """
        return self.mount_path.is_dir() and self.root.is_dir()
