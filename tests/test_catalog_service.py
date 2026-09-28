"""Tests for catalog service pure functions."""

import hashlib

from src.modules.catalog.service import calculate_file_hash


class TestFileHash:
    """Test file hash calculation."""

    def test_hash_bytes(self):
        """Hash of known bytes matches SHA256."""
        data = b"hello world"
        expected = hashlib.sha256(data).hexdigest()
        assert calculate_file_hash(data) == expected

    def test_hash_empty(self):
        """Hash of empty bytes is valid."""
        h = calculate_file_hash(b"")
        assert len(h) == 64  # SHA256 hex digest length

    def test_hash_deterministic(self):
        """Same input produces same hash."""
        data = b"test data for hashing"
        assert calculate_file_hash(data) == calculate_file_hash(data)

    def test_hash_different(self):
        """Different inputs produce different hashes."""
        assert calculate_file_hash(b"a") != calculate_file_hash(b"b")

    def test_hash_large_input(self):
        """Hash works on large input."""
        data = b"x" * 1_000_000
        h = calculate_file_hash(data)
        assert isinstance(h, str)
        assert len(h) == 64
