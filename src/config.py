"""Configuration loader for media-library skill."""

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_CONFIG: dict[str, Any] | None = None


def load_config() -> dict[str, Any]:
    """Load configuration from YAML file.

    Searches for config/media-library.yaml relative to the project root.
    Falls back to sensible defaults if file is missing.

    Returns:
        Configuration dictionary.
    """
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    config_path = Path(__file__).parent.parent / "config" / "media-library.yaml"
    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}, using defaults")
        _CONFIG = _get_defaults()
        return _CONFIG

    with open(config_path) as f:
        _CONFIG = yaml.safe_load(f) or {}

    logger.info(f"Loaded config from {config_path}")
    return _CONFIG


def get_vault_url() -> str:
    """Get Vault endpoint URL from config.

    Returns:
        Vault URL string.
    """
    cfg = load_config()
    return cfg.get("endpoints", {}).get("vault", "http://10.0.0.44:8050")


def get_db_config() -> dict[str, Any]:
    """Get database configuration.

    Returns:
        Database config dict with host, port, name, user, password_vault_key.
    """
    cfg = load_config()
    return cfg.get("database", _get_defaults()["database"])


def get_storage_config() -> dict[str, Any]:
    """Get storage configuration.

    Returns:
        Storage config dict with default_backend and backends.
    """
    cfg = load_config()
    return cfg.get("storage", _get_defaults()["storage"])


def get_thumbnails_config() -> dict[str, Any]:
    """Get thumbnails configuration.

    Returns:
        Thumbnails config dict with path, size, format.
    """
    cfg = load_config()
    defaults = _get_defaults()["thumbnails"]
    thumb_cfg = cfg.get("thumbnails", defaults)
    # Allow env var override for thumbnail path
    env_path = os.getenv("MEDIA_LIBRARY_THUMB_PATH")
    if env_path:
        thumb_cfg["path"] = env_path
    return thumb_cfg


def _get_defaults() -> dict[str, Any]:
    """Return default configuration values.

    Returns:
        Default config dictionary.
    """
    return {
        "storage": {
            "default_backend": "nas",
            "backends": {
                "nas": {"enabled": True, "mount_path": "/mnt/ml-store", "base_dir": "media-library"},
                "dropbox": {"enabled": True, "base_path": "/media-library"},
            },
        },
        "database": {
            "type": "mariadb",
            "host": "10.0.0.44",
            "port": 3306,
            "name": "digikam",
            "user": "digikam",
            "password_vault_key": "digikam_db_password",
            "pool_size": 5,
        },
        "thumbnails": {
            "path": "/opt/onyx/data/media-library/thumbnails",
            "size": 320,
            "format": "webp",
            "quality": 80,
        },
        "endpoints": {
            "vault": "http://10.0.0.44:8050",
            "paper_reader": "http://10.0.0.21:8462",
            "llm_router": "http://localhost:8055",
        },
        "settings": {
            "groq_model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "max_upload_size_mb": 100,
            "service_host": "10.0.0.21",
            "service_port": 8202,
        },
    }


CONFIG = load_config()
