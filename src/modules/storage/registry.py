"""Storage backend registry.

Central factory for creating and retrieving storage backends
based on configuration.
"""

import logging
from typing import Any

from src.config import get_storage_config
from src.modules.storage.dropbox_backend import DropboxStorage
from src.modules.storage.nas import NASStorage

logger = logging.getLogger(__name__)

_backends: dict[str, Any] = {}
_default_name: str = "nas"


def init_backends() -> None:
    """Initialize storage backends from configuration.

    Reads config/media-library.yaml and creates backend instances
    for each enabled backend.
    """
    global _default_name
    cfg = get_storage_config()
    _default_name = cfg.get("default_backend", "nas")

    backends_cfg = cfg.get("backends", {})

    # NAS backend
    nas_cfg = backends_cfg.get("nas", {})
    if nas_cfg.get("enabled", False):
        nas = NASStorage(
            mount_path=nas_cfg.get("mount_path", "/mnt/ml-store"),
            base_dir=nas_cfg.get("base_dir", "media-library"),
        )
        _backends["nas"] = nas
        logger.info(f"Storage: NAS backend initialized (mounted={nas.is_mounted()})")

    # Dropbox backend
    dbx_cfg = backends_cfg.get("dropbox", {})
    if dbx_cfg.get("enabled", False):
        dbx = DropboxStorage(base_path=dbx_cfg.get("base_path", "/media-library"))
        _backends["dropbox"] = dbx
        logger.info("Storage: Dropbox backend initialized")

    if _default_name not in _backends:
        available = list(_backends.keys())
        if available:
            _default_name = available[0]
            logger.warning(f"Default backend '{cfg.get('default_backend')}' not available, using '{_default_name}'")
        else:
            logger.error("No storage backends available!")


def get_backend(name: str) -> Any:
    """Get a storage backend by name.

    Args:
        name: Backend name ('nas' or 'dropbox').

    Returns:
        StorageBackend instance.

    Raises:
        KeyError: If backend not found.
    """
    if name not in _backends:
        raise KeyError(f"Storage backend '{name}' not found. Available: {list(_backends.keys())}")
    return _backends[name]


def get_default() -> Any:
    """Get the default storage backend.

    Returns:
        Default StorageBackend instance.

    Raises:
        RuntimeError: If no backends are initialized.
    """
    if not _backends:
        raise RuntimeError("No storage backends initialized. Call init_backends() first.")
    return _backends[_default_name]


def get_default_name() -> str:
    """Get the name of the default backend.

    Returns:
        Default backend name string.
    """
    return _default_name


def list_backends() -> list[str]:
    """List available backend names.

    Returns:
        List of backend name strings.
    """
    return list(_backends.keys())
