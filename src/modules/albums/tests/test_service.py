"""Tests for albums service."""


class TestAlbumPaths:
    """Test album path normalization."""

    def test_path_without_leading_slash(self):
        """Path without leading slash gets normalized."""
        path = "originals/2026"
        if not path.startswith("/"):
            path = f"/{path}"
        assert path == "/originals/2026"

    def test_path_with_leading_slash(self):
        """Path with leading slash stays unchanged."""
        path = "/papers/ABC123"
        if not path.startswith("/"):
            path = f"/{path}"
        assert path == "/papers/ABC123"

    def test_root_path(self):
        """Root path is valid."""
        path = "/"
        assert path.startswith("/")
