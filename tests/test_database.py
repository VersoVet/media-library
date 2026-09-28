"""Tests for database module constants and helpers."""

from src.database import (
    ALBUMROOT_TYPE_NETWORK,
    ALBUMROOT_TYPE_SPECIFIC,
    ALBUMROOT_TYPE_VOLUME,
    IMAGE_CATEGORY_AUDIO,
    IMAGE_CATEGORY_IMAGE,
    IMAGE_CATEGORY_OTHER,
    IMAGE_CATEGORY_VIDEO,
    IMAGE_STATUS_REMOVED,
    IMAGE_STATUS_TRASHED,
    IMAGE_STATUS_VISIBLE,
)


class TestDigikamConstants:
    """Test Digikam-specific constants."""

    def test_image_status_values(self):
        """Image status values match Digikam convention."""
        assert IMAGE_STATUS_VISIBLE == 1
        assert IMAGE_STATUS_REMOVED == 2
        assert IMAGE_STATUS_TRASHED == 3

    def test_image_category_values(self):
        """Image category values match Digikam convention."""
        assert IMAGE_CATEGORY_IMAGE == 1
        assert IMAGE_CATEGORY_AUDIO == 2
        assert IMAGE_CATEGORY_VIDEO == 3
        assert IMAGE_CATEGORY_OTHER == 4

    def test_albumroot_type_values(self):
        """AlbumRoot type values match Digikam convention."""
        assert ALBUMROOT_TYPE_VOLUME == 1
        assert ALBUMROOT_TYPE_SPECIFIC == 2
        assert ALBUMROOT_TYPE_NETWORK == 3

    def test_visible_is_default_status(self):
        """Visible is the first (default) status."""
        assert IMAGE_STATUS_VISIBLE < IMAGE_STATUS_REMOVED
        assert IMAGE_STATUS_REMOVED < IMAGE_STATUS_TRASHED
