"""Tests for tagger module."""

import pytest


class TestTaggerService:
    """Test LLM-based tag suggestion."""

    @pytest.mark.asyncio
    async def test_fallback_tags_generation(self):
        """Test fallback tag generation from metadata."""
        from src.modules.tagger.service import _fallback_tags

        metadata = {
            "format": "JPEG",
            "width": 1920,
            "height": 1080,
            "exif": {"make": "Canon", "model": "EOS R5"},
        }
        tags = await _fallback_tags(metadata)
        assert isinstance(tags, list)
        assert len(tags) > 0
        assert "jpeg" in tags or "JPEG" in str(tags).lower()
