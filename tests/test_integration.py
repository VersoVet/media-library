"""Integration tests for media-library skill."""

import json
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.database import init_db


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.mark.asyncio
async def test_health():
    """Test health endpoint."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "db" in data


@pytest.mark.asyncio
async def test_info():
    """Test info endpoint."""
    client = TestClient(app)
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "total_media" in data


@pytest.mark.asyncio
async def test_create_source():
    """Test creating a scan source."""
    client = TestClient(app)

    payload = {
        "name": "Test Source",
        "source_type": "dropbox",
        "config": {"path": "/test/"},
        "enabled": True,
        "recursive": True,
        "auto_tag": True,
        "cron_schedule": "0 0 * * *",
    }

    response = client.post("/api/sources", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Source"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_sources():
    """Test listing scan sources."""
    client = TestClient(app)

    # Create a source first
    payload = {
        "name": "Test Source",
        "source_type": "local",
        "config": {"path": "/tmp/"},
        "enabled": True,
    }
    client.post("/api/sources", json=payload)

    # List sources
    response = client.get("/api/sources")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_search_empty():
    """Test search with empty database."""
    client = TestClient(app)

    response = client.get("/api/search?q=test")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_tags():
    """Test listing tags."""
    client = TestClient(app)

    response = client.get("/api/tags")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_root():
    """Test root endpoint."""
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "docs" in data
