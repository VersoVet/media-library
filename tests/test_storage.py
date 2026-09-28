"""Tests for storage backends."""

import pytest

from src.modules.storage.nas import NASStorage
from src.modules.storage.protocol import StorageBackend


class TestNASStorage:
    """Test NAS storage backend."""

    def test_nas_implements_protocol(self):
        """NAS storage implements StorageBackend protocol."""
        nas = NASStorage(mount_path="/tmp", base_dir="test")
        assert isinstance(nas, StorageBackend)

    def test_nas_name(self):
        """NAS backend has correct name."""
        nas = NASStorage(mount_path="/tmp", base_dir="test")
        assert nas.name == "nas"

    def test_nas_root_path(self):
        """NAS root path is mount_path/base_dir."""
        nas = NASStorage(mount_path="/mnt/nas", base_dir="media")
        assert str(nas.root) == "/mnt/nas/media"

    def test_nas_root_path_empty_base_dir(self):
        """NAS root path with empty base_dir."""
        nas = NASStorage(mount_path="/mnt/media-library", base_dir="")
        assert str(nas.root) == "/mnt/media-library"

    def test_nas_traversal_protection(self):
        """NAS storage prevents directory traversal."""
        nas = NASStorage(mount_path="/tmp/test_nas", base_dir="media")
        with pytest.raises(ValueError, match="traversal"):
            nas._full_path("../../etc/passwd")

    def test_nas_full_path_valid(self):
        """NAS storage resolves valid paths."""
        nas = NASStorage(mount_path="/tmp", base_dir="test")
        path = nas._full_path("originals/photo.jpg")
        assert "originals/photo.jpg" in str(path)

    def test_nas_is_mounted_false(self):
        """NAS reports not mounted for non-existent path."""
        nas = NASStorage(mount_path="/nonexistent/path", base_dir="test")
        assert nas.is_mounted() is False


class TestStorageRegistry:
    """Test storage registry."""

    def test_list_backends_returns_list(self):
        """Registry returns a list of backend names."""
        from src.modules.storage.registry import list_backends

        backends = list_backends()
        assert isinstance(backends, list)

    def test_init_backends(self):
        """Init backends loads from config."""
        from src.modules.storage.registry import init_backends, list_backends

        init_backends()
        backends = list_backends()
        assert "nas" in backends

    def test_get_default_name(self):
        """Default backend name is nas."""
        from src.modules.storage.registry import get_default_name, init_backends

        init_backends()
        assert get_default_name() == "nas"

    def test_get_backend_invalid(self):
        """Getting non-existent backend raises KeyError."""
        from src.modules.storage.registry import get_backend, init_backends

        init_backends()
        with pytest.raises(KeyError):
            get_backend("nonexistent")


class TestDropboxStorage:
    """Test Dropbox storage backend."""

    def test_dropbox_name(self):
        """Dropbox backend has correct name."""
        from src.modules.storage.dropbox_backend import DropboxStorage

        dbx = DropboxStorage(base_path="/media-library")
        assert dbx.name == "dropbox"

    def test_dropbox_path_construction(self):
        """Dropbox path combines base_path and relative path."""
        from src.modules.storage.dropbox_backend import DropboxStorage

        dbx = DropboxStorage(base_path="/media-library")
        assert dbx._dropbox_path("originals/photo.jpg") == "/media-library/originals/photo.jpg"

    def test_dropbox_implements_protocol(self):
        """Dropbox storage implements StorageBackend protocol."""
        from src.modules.storage.dropbox_backend import DropboxStorage

        dbx = DropboxStorage()
        assert isinstance(dbx, StorageBackend)
