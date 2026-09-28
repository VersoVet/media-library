"""Tests for storage module."""

import pytest

from src.modules.storage.nas import NASStorage
from src.modules.storage.protocol import StorageBackend
from src.modules.storage.registry import get_default_name, init_backends, list_backends


class TestNASStorageUnit:
    """Unit tests for NASStorage."""

    def test_instantiation(self):
        """NASStorage can be instantiated."""
        nas = NASStorage(mount_path="/tmp", base_dir="test")
        assert nas.name == "nas"

    def test_protocol_compliance(self):
        """NASStorage satisfies StorageBackend protocol."""
        assert isinstance(NASStorage(mount_path="/tmp", base_dir="t"), StorageBackend)

    def test_traversal_blocked(self):
        """Directory traversal raises ValueError."""
        nas = NASStorage(mount_path="/tmp/safe", base_dir="data")
        with pytest.raises(ValueError):
            nas._full_path("../../../etc/shadow")

    def test_normal_path_resolves(self):
        """Normal relative path resolves correctly."""
        nas = NASStorage(mount_path="/tmp", base_dir="data")
        p = nas._full_path("originals/2026/09/abc.jpg")
        assert "originals" in str(p)

    def test_is_mounted_nonexistent(self):
        """Reports not mounted for fake path."""
        nas = NASStorage(mount_path="/does_not_exist_xyz", base_dir="x")
        assert not nas.is_mounted()


class TestRegistryUnit:
    """Unit tests for storage registry."""

    def test_init_creates_backends(self):
        """init_backends populates registry."""
        init_backends()
        assert len(list_backends()) > 0

    def test_default_is_nas(self):
        """Default backend is NAS."""
        init_backends()
        assert get_default_name() == "nas"

    def test_list_contains_nas(self):
        """Backend list includes nas."""
        init_backends()
        assert "nas" in list_backends()
