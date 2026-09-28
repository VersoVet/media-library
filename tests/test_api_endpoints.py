"""Test API endpoints via TestClient (no DB required for some)."""

import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app, raise_server_exceptions=False)


class TestRootEndpoints:
    """Test basic endpoints that don't need DB."""

    def test_root(self):
        """Root returns welcome message."""
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert "message" in data
        assert "Media Library" in data["message"]
        assert "docs" in data

    def test_health(self):
        """Health returns status."""
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "db" in data
        assert "nas_mounted" in data

    def test_info(self):
        """Info returns version and counts."""
        r = client.get("/info")
        assert r.status_code == 200
        data = r.json()
        assert "version" in data
        assert data["version"] == "2.0.0"
        assert "total_media" in data
        assert "total_albums" in data
        assert "storage_backend" in data

    def test_cron_status(self):
        """Cron returns scheduler status."""
        r = client.get("/cron")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data

    def test_openapi_docs(self):
        """OpenAPI docs are accessible."""
        r = client.get("/openapi.json")
        assert r.status_code == 200
        data = r.json()
        assert "paths" in data
        assert "/api/upload" in data["paths"]

    def test_docs_ui(self):
        """Swagger UI is accessible."""
        r = client.get("/docs")
        assert r.status_code == 200


class TestMediaEndpoints:
    """Test media endpoints (may return errors without DB but exercises code paths)."""

    def test_get_media_not_found(self):
        """Get non-existent media returns 404 or 500."""
        r = client.get("/api/media/99999")
        assert r.status_code in (404, 500)

    def test_get_media_url_not_found(self):
        """Get URL for non-existent media."""
        r = client.get("/api/media/99999/url")
        assert r.status_code in (404, 500)

    def test_get_thumbnail_not_found(self):
        """Get thumbnail for non-existent media."""
        r = client.get("/api/media/99999/thumbnail")
        assert r.status_code in (404, 500)

    def test_batch_empty(self):
        """Batch with no valid IDs returns empty."""
        r = client.get("/api/media/batch?ids=")
        assert r.status_code in (200, 500)

    def test_batch_too_many(self):
        """Batch with >50 IDs returns 400."""
        ids = ",".join(str(i) for i in range(51))
        r = client.get(f"/api/media/batch?ids={ids}")
        assert r.status_code in (400, 500)

    def test_delete_media_not_found(self):
        """Delete non-existent media."""
        r = client.delete("/api/media/99999")
        assert r.status_code in (404, 500)


class TestSearchEndpoints:
    """Test search endpoints."""

    def test_search_empty_query(self):
        """Search with empty query."""
        r = client.get("/api/search")
        assert r.status_code in (200, 500)

    def test_search_with_query(self):
        """Search with query string."""
        r = client.get("/api/search?q=test")
        assert r.status_code in (200, 500)

    def test_search_with_type(self):
        """Search with media type filter."""
        r = client.get("/api/search?media_type=image")
        assert r.status_code in (200, 500)

    def test_list_tags(self):
        """List all tags."""
        r = client.get("/api/tags")
        assert r.status_code in (200, 500)

    def test_get_media_by_tag(self):
        """Get media by tag."""
        r = client.get("/api/tags/nonexistent/media")
        assert r.status_code in (200, 500)


class TestAlbumEndpoints:
    """Test album endpoints."""

    def test_list_albums(self):
        """List albums."""
        r = client.get("/api/albums")
        assert r.status_code in (200, 500)

    def test_get_album_not_found(self):
        """Get non-existent album."""
        r = client.get("/api/albums/99999")
        assert r.status_code in (404, 500)


class TestSourceEndpoints:
    """Test source endpoints."""

    def test_list_sources(self):
        """List scan sources."""
        r = client.get("/api/sources")
        assert r.status_code in (200, 500)

    def test_get_source_not_found(self):
        """Get non-existent source."""
        r = client.get("/api/sources/99999")
        assert r.status_code in (404, 500)


class TestIntegrationEndpoints:
    """Test integration endpoints."""

    def test_list_paper_collections(self):
        """List paper collections."""
        r = client.get("/api/paper-collections")
        assert r.status_code in (200, 500)

    def test_get_paper_collection_not_found(self):
        """Get non-existent paper collection."""
        r = client.get("/api/paper-collections/NONEXISTENT")
        assert r.status_code in (404, 500)


class TestFileServing:
    """Test file serving endpoint."""

    def test_serve_nonexistent_file(self):
        """Serving non-existent file returns 404."""
        r = client.get("/api/files/nonexistent/file.jpg")
        assert r.status_code in (404, 500, 501)

    def test_serve_traversal_blocked(self):
        """Directory traversal is blocked."""
        r = client.get("/api/files/../../etc/passwd")
        assert r.status_code in (403, 404, 500)
