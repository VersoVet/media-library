"""Storage backend protocol definition."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for pluggable storage backends.

    Each backend handles file storage (upload, download, delete)
    and URL generation for serving files.
    """

    name: str

    async def upload(self, file_bytes: bytes, dest_path: str) -> dict[str, Any]:
        """Upload file bytes to the backend.

        Args:
            file_bytes: File content.
            dest_path: Relative path within the backend namespace.

        Returns:
            Metadata dict with at least 'path' and 'size' keys.
        """
        ...

    async def download(self, path: str) -> bytes:
        """Download file from backend.

        Args:
            path: Path within the backend namespace.

        Returns:
            File bytes.
        """
        ...

    async def get_url(self, path: str) -> str:
        """Get a servable URL for the file.

        Args:
            path: Path within the backend namespace.

        Returns:
            URL string (permanent or temporary depending on backend).
        """
        ...

    async def exists(self, path: str) -> bool:
        """Check if file exists at path.

        Args:
            path: Path within the backend namespace.

        Returns:
            True if file exists.
        """
        ...

    async def delete(self, path: str) -> bool:
        """Delete file from backend.

        Args:
            path: Path to delete.

        Returns:
            True if deleted, False if not found.
        """
        ...
