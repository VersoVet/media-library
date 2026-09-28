"""Tests for configuration loader."""


class TestConfigLoader:
    """Test config loading and defaults."""

    def test_load_config_returns_dict(self):
        """Config loader returns a dictionary."""
        from src.config import load_config

        config = load_config()
        assert isinstance(config, dict)

    def test_config_has_storage(self):
        """Config contains storage section."""
        from src.config import load_config

        config = load_config()
        assert "storage" in config

    def test_config_has_database(self):
        """Config contains database section."""
        from src.config import load_config

        config = load_config()
        assert "database" in config

    def test_config_has_endpoints(self):
        """Config contains endpoints section."""
        from src.config import load_config

        config = load_config()
        assert "endpoints" in config

    def test_get_storage_config(self):
        """Storage config returns backends."""
        from src.config import get_storage_config

        cfg = get_storage_config()
        assert "default_backend" in cfg
        assert "backends" in cfg
        assert "nas" in cfg["backends"]

    def test_get_db_config(self):
        """DB config returns MariaDB settings."""
        from src.config import get_db_config

        cfg = get_db_config()
        assert cfg["type"] == "mariadb"
        assert "host" in cfg
        assert "port" in cfg
        assert "name" in cfg

    def test_get_thumbnails_config(self):
        """Thumbnails config returns path and size."""
        from src.config import get_thumbnails_config

        cfg = get_thumbnails_config()
        assert "path" in cfg
        assert "size" in cfg
        assert cfg["size"] == 320

    def test_nas_disabled_dropbox(self):
        """Dropbox should be disabled in config."""
        from src.config import get_storage_config

        cfg = get_storage_config()
        dbx = cfg["backends"].get("dropbox", {})
        assert dbx.get("enabled") is False

    def test_nas_mount_path(self):
        """NAS mount path points to media-library."""
        from src.config import get_storage_config

        cfg = get_storage_config()
        nas = cfg["backends"]["nas"]
        assert "/media-library" in nas["mount_path"]

    def test_default_backend_is_nas(self):
        """Default storage backend is NAS."""
        from src.config import get_storage_config

        cfg = get_storage_config()
        assert cfg["default_backend"] == "nas"
