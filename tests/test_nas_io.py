"""Tests for NAS storage I/O operations."""

import tempfile

import pytest

from src.modules.storage.nas import NASStorage


@pytest.fixture
def tmp_nas():
    """Create a temporary NAS-like directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        nas = NASStorage(mount_path=tmpdir, base_dir="media")
        nas.root.mkdir(parents=True, exist_ok=True)
        yield nas


class TestNASUpload:
    """Test NAS upload operations."""

    @pytest.mark.asyncio
    async def test_upload_creates_file(self, tmp_nas):
        """Upload creates file on disk."""
        result = await tmp_nas.upload(b"test content", "test.txt")
        assert result["size"] == 12
        assert (tmp_nas.root / "test.txt").exists()

    @pytest.mark.asyncio
    async def test_upload_creates_dirs(self, tmp_nas):
        """Upload creates parent directories."""
        await tmp_nas.upload(b"data", "a/b/c/file.txt")
        assert (tmp_nas.root / "a" / "b" / "c" / "file.txt").exists()

    @pytest.mark.asyncio
    async def test_upload_metadata(self, tmp_nas):
        """Upload returns correct metadata."""
        result = await tmp_nas.upload(b"x" * 100, "photo.jpg")
        assert result["path"] == "photo.jpg"
        assert result["size"] == 100
        assert result["backend"] == "nas"


class TestNASDownload:
    """Test NAS download operations."""

    @pytest.mark.asyncio
    async def test_download_existing(self, tmp_nas):
        """Download returns file content."""
        await tmp_nas.upload(b"hello world", "dl_test.txt")
        data = await tmp_nas.download("dl_test.txt")
        assert data == b"hello world"

    @pytest.mark.asyncio
    async def test_download_nonexistent(self, tmp_nas):
        """Download raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            await tmp_nas.download("nonexistent.txt")


class TestNASExists:
    """Test NAS exists check."""

    @pytest.mark.asyncio
    async def test_exists_true(self, tmp_nas):
        """Exists returns True for uploaded file."""
        await tmp_nas.upload(b"data", "exists_test.txt")
        assert await tmp_nas.exists("exists_test.txt") is True

    @pytest.mark.asyncio
    async def test_exists_false(self, tmp_nas):
        """Exists returns False for missing file."""
        assert await tmp_nas.exists("no_such_file.txt") is False


class TestNASDelete:
    """Test NAS delete operations."""

    @pytest.mark.asyncio
    async def test_delete_existing(self, tmp_nas):
        """Delete removes file and returns True."""
        await tmp_nas.upload(b"data", "del_test.txt")
        result = await tmp_nas.delete("del_test.txt")
        assert result is True
        assert not (tmp_nas.root / "del_test.txt").exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, tmp_nas):
        """Delete returns False for missing file."""
        result = await tmp_nas.delete("missing.txt")
        assert result is False


class TestNASGetUrl:
    """Test NAS URL generation."""

    @pytest.mark.asyncio
    async def test_url_format(self, tmp_nas):
        """URL points to the API file-serving endpoint."""
        url = await tmp_nas.get_url("originals/photo.jpg")
        assert "/api/files/" in url
        assert "originals/photo.jpg" in url


class TestNASMounted:
    """Test NAS mount detection."""

    def test_mounted_with_real_dir(self, tmp_nas):
        """Reports mounted for existing directory."""
        assert tmp_nas.is_mounted() is True

    def test_not_mounted_fake_dir(self):
        """Reports not mounted for fake directory."""
        nas = NASStorage(mount_path="/nonexistent_xyz_123", base_dir="t")
        assert nas.is_mounted() is False
