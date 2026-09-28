"""Tests for integrations service."""

from src.modules.integrations.service import _ext_from_content_type


class TestExtFromContentType:
    """Test file extension detection from content type."""

    def test_png(self):
        """PNG content type returns .png."""
        assert _ext_from_content_type("image/png") == ".png"

    def test_jpeg(self):
        """JPEG content type returns .jpg."""
        assert _ext_from_content_type("image/jpeg") == ".jpg"

    def test_webp(self):
        """WebP content type returns .webp."""
        assert _ext_from_content_type("image/webp") == ".webp"

    def test_gif(self):
        """GIF content type returns .gif."""
        assert _ext_from_content_type("image/gif") == ".gif"

    def test_tiff(self):
        """TIFF content type returns .tiff."""
        assert _ext_from_content_type("image/tiff") == ".tiff"

    def test_svg(self):
        """SVG content type returns .svg."""
        assert _ext_from_content_type("image/svg+xml") == ".svg"

    def test_unknown_defaults_to_png(self):
        """Unknown content type defaults to .png."""
        assert _ext_from_content_type("application/octet-stream") == ".png"

    def test_with_charset(self):
        """Content type with charset parameter is handled."""
        assert _ext_from_content_type("image/jpeg; charset=utf-8") == ".jpg"
