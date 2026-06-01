"""Pydantic models for media-library skill."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Tag(BaseModel):
    """Tag model."""

    id: int | None = None
    name: str


class MediaMetadata(BaseModel):
    """Media metadata (EXIF, ffprobe, etc.)."""

    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    exif: dict[str, Any] = Field(default_factory=dict)
    codec: str | None = None
    fps: float | None = None


class MediaItem(BaseModel):
    """Media item in library."""

    id: str
    title: str
    description: str = ""
    media_type: str  # "image" or "video"
    mime_type: str
    dropbox_path: str
    source_id: int | None = None
    source_path: str | None = None
    file_size: int
    metadata: MediaMetadata = Field(default_factory=MediaMetadata)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class UploadRequest(BaseModel):
    """Upload request (multipart handled separately)."""

    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class UploadResponse(BaseModel):
    """Upload response."""

    id: str
    title: str
    dropbox_path: str
    file_size: int
    media_type: str
    created_at: datetime


class SearchQuery(BaseModel):
    """Search query parameters."""

    q: str = ""
    media_type: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchResult(BaseModel):
    """Search result."""

    total: int
    items: list[MediaItem]


class TagSuggestion(BaseModel):
    """Tag suggestions for a media."""

    media_id: str
    suggested_tags: list[str]
    confidence: float | None = None


class ScanSourceConfig(BaseModel):
    """Source configuration (polymorphic by type)."""

    pass


class DropboxSourceConfig(ScanSourceConfig):
    """Dropbox source config."""

    path: str = "/"


class LocalSourceConfig(ScanSourceConfig):
    """Local filesystem source config."""

    path: str


class SSHSourceConfig(ScanSourceConfig):
    """SSH source config."""

    host: str
    port: int = 22
    user: str
    key: str  # reference to Vault key name (e.g., "ssh_key_axon")
    path: str


class ScanSource(BaseModel):
    """Scan source (Dropbox/local/SSH)."""

    id: int | None = None
    name: str
    source_type: str  # "dropbox", "local", "ssh"
    config: dict[str, Any]  # serialized config
    enabled: bool = True
    recursive: bool = True
    auto_tag: bool = True
    cron_schedule: str = "0 */6 * * *"
    last_scan_at: datetime | None = None
    last_scan_status: str | None = None  # "ok", "error", "running"


class ScanLog(BaseModel):
    """Scan log entry."""

    id: int | None = None
    source_id: int
    started_at: datetime
    finished_at: datetime | None = None
    files_found: int = 0
    files_imported: int = 0
    files_skipped: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)


class SyncReport(BaseModel):
    """Sync report after scanning a source."""

    source_id: int
    files_found: int
    files_imported: int
    files_skipped: int
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    db: str
    dropbox: str | None = None


class InfoResponse(BaseModel):
    """Info endpoint response."""

    version: str = "1.0.0"
    total_media: int
    total_tags: int
    total_sources: int
