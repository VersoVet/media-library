"""Tests for Pydantic models."""

from datetime import datetime

from src.models import (
    Album,
    AlbumCreate,
    CopyToRequest,
    HealthResponse,
    InfoResponse,
    MediaBatchItem,
    MediaBatchResponse,
    MediaItem,
    MediaUrl,
    PaperCollection,
    PaperFigure,
    PaperReaderPayload,
    ScanSource,
    SearchResult,
    Tag,
    UploadResponse,
)


class TestMediaItem:
    """Test MediaItem model."""

    def test_create_minimal(self):
        """Create MediaItem with minimal fields."""
        item = MediaItem(id=1, name="test.jpg")
        assert item.id == 1
        assert item.name == "test.jpg"
        assert item.media_type == "image"
        assert item.storage_backend == "nas"

    def test_create_full(self):
        """Create MediaItem with all fields."""
        item = MediaItem(
            id=1,
            name="photo.jpg",
            title="Test Photo",
            media_type="image",
            mime_type="image/jpeg",
            album_id=2,
            storage_backend="nas",
            storage_path="originals/2026/09/abc123.jpg",
            file_size=1024,
            width=1920,
            height=1080,
            tags=["test", "photo"],
        )
        assert item.width == 1920
        assert len(item.tags) == 2

    def test_defaults(self):
        """MediaItem has correct defaults."""
        item = MediaItem(id=1, name="test.jpg")
        assert item.tags == []
        assert item.file_size == 0
        assert item.description == ""


class TestAlbum:
    """Test Album model."""

    def test_create_album(self):
        """Create Album with path."""
        album = Album(relative_path="/originals")
        assert album.relative_path == "/originals"
        assert album.album_root == 1
        assert album.media_count == 0

    def test_album_create_request(self):
        """AlbumCreate request model."""
        req = AlbumCreate(relative_path="/papers/ABC123", caption="Test Article")
        assert req.relative_path == "/papers/ABC123"
        assert req.caption == "Test Article"


class TestTag:
    """Test Tag model."""

    def test_create_tag(self):
        """Create tag with defaults."""
        tag = Tag(name="radiology")
        assert tag.name == "radiology"
        assert tag.pid == 0

    def test_hierarchical_tag(self):
        """Create tag with parent."""
        tag = Tag(name="thorax", pid=5)
        assert tag.pid == 5


class TestPaperModels:
    """Test paper-reader integration models."""

    def test_paper_figure(self):
        """Create PaperFigure."""
        fig = PaperFigure(
            figure_id="fig_001",
            label="Figure 1",
            caption="Test caption",
            native_url="http://example.com/fig.png",
        )
        assert fig.figure_id == "fig_001"

    def test_paper_payload(self):
        """Create PaperReaderPayload."""
        payload = PaperReaderPayload(
            zotero_key="ABC123",
            article_title="Test Article",
            figures=[
                PaperFigure(
                    figure_id="fig_001",
                    label="Figure 1",
                    native_url="http://example.com/fig.png",
                ),
            ],
        )
        assert payload.zotero_key == "ABC123"
        assert len(payload.figures) == 1

    def test_paper_collection(self):
        """Create PaperCollection."""
        pc = PaperCollection(zotero_key="XYZ", article_title="Some Paper")
        assert pc.album_id is None


class TestResponseModels:
    """Test response models."""

    def test_media_url(self):
        """MediaUrl response."""
        url = MediaUrl(url="http://host/api/files/test.jpg", media_id=1, filename="test.jpg")
        assert url.url.startswith("http")

    def test_batch_response(self):
        """MediaBatchResponse with items."""
        resp = MediaBatchResponse(
            media=[
                MediaBatchItem(
                    id=1,
                    title="Test",
                    media_type="image",
                    url="http://x",
                    thumbnail_url="/api/media/1/thumbnail",
                ),
            ]
        )
        assert len(resp.media) == 1

    def test_upload_response(self):
        """UploadResponse model."""
        resp = UploadResponse(
            id=1,
            title="Test",
            storage_path="originals/test.jpg",
            storage_backend="nas",
            file_size=1024,
            media_type="image",
            created_at=datetime.now(),
        )
        assert resp.storage_backend == "nas"

    def test_health_response(self):
        """HealthResponse model."""
        hr = HealthResponse(status="ok", db="ok", nas_mounted=True)
        assert hr.nas_mounted is True

    def test_info_response(self):
        """InfoResponse model."""
        ir = InfoResponse(
            total_media=100,
            total_tags=20,
            total_albums=5,
            total_sources=3,
            storage_backend="nas",
        )
        assert ir.version == "2.0.0"

    def test_scan_source(self):
        """ScanSource model with NAS type."""
        src = ScanSource(
            name="Test",
            source_type="nas",
            config={"path": "/data"},
        )
        assert src.source_type == "nas"
        assert src.enabled is True

    def test_search_result(self):
        """SearchResult model."""
        sr = SearchResult(total=0, items=[])
        assert sr.total == 0

    def test_copy_to_request(self):
        """CopyToRequest model."""
        req = CopyToRequest(destination_folder="/conferences/TPLO/")
        assert req.destination_folder.endswith("/")
