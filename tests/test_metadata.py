"""Tests for metadata extraction."""

from src.modules.catalog.metadata import (
    extract_image_metadata,
    get_media_type,
    is_supported_image,
    is_supported_video,
)


class TestMediaType:
    """Test media type detection."""

    def test_image_jpeg(self):
        """JPEG is detected as image."""
        assert get_media_type("image/jpeg") == "image"

    def test_image_png(self):
        """PNG is detected as image."""
        assert get_media_type("image/png") == "image"

    def test_video_mp4(self):
        """MP4 is detected as video."""
        assert get_media_type("video/mp4") == "video"

    def test_unknown_type(self):
        """Unknown MIME type returns unknown."""
        assert get_media_type("application/pdf") == "unknown"

    def test_text_type(self):
        """Text MIME type returns unknown."""
        assert get_media_type("text/plain") == "unknown"


class TestSupportedFormats:
    """Test format support detection."""

    def test_supported_images(self):
        """Common image formats are supported."""
        assert is_supported_image("image/jpeg") is True
        assert is_supported_image("image/png") is True
        assert is_supported_image("image/webp") is True
        assert is_supported_image("image/gif") is True

    def test_unsupported_image(self):
        """BMP is not in supported list."""
        assert is_supported_image("image/bmp") is False

    def test_supported_videos(self):
        """Common video formats are supported."""
        assert is_supported_video("video/mp4") is True
        assert is_supported_video("video/webm") is True
        assert is_supported_video("video/quicktime") is True

    def test_unsupported_video(self):
        """FLV is not supported."""
        assert is_supported_video("video/x-flv") is False


class TestImageMetadata:
    """Test image metadata extraction."""

    def test_extract_from_valid_png(self):
        """Extract metadata from a minimal valid PNG."""
        # 1x1 red PNG
        import base64

        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        img_bytes = base64.b64decode(png_b64)

        meta = extract_image_metadata(img_bytes)
        assert meta["width"] == 1
        assert meta["height"] == 1
        assert meta["format"] == "PNG"

    def test_extract_from_invalid_bytes(self):
        """Extract metadata from invalid bytes returns defaults."""
        meta = extract_image_metadata(b"not an image")
        assert meta.get("format") == "unknown"

    def test_extract_from_valid_jpeg(self):
        """Extract metadata from a minimal JPEG."""
        import io

        from PIL import Image

        img = Image.new("RGB", (100, 50), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        img_bytes = buf.getvalue()

        meta = extract_image_metadata(img_bytes)
        assert meta["width"] == 100
        assert meta["height"] == 50
        assert meta["format"] == "JPEG"
