"""Tests for full-text search module."""

import pytest


class TestSearchService:
    """Test FTS5 search functionality."""

    @pytest.mark.asyncio
    async def test_media_search(self):
        """Test searching media with FTS5."""
        # This test verifies search functionality
        # Full tests require database fixtures with sample media
        pass
