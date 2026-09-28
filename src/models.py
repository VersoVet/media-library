"""Pydantic models for media-library skill (Digikam-compatible)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# -- Digikam core models --


class AlbumRoot(BaseModel):
    """Album root (collection mount point)."""

    id: int
    label: str | None = None
    status: int = 0
    type: int = 3  # 3 = network
    identifier: str | None = None
    specific_path: str | None = None


class Album(BaseModel):
    """Album (directory in Digikam collection)."""

    id: int | None = None
    album_root: int = 1
    relative_path: str
    date: datetime | None = None
    caption: str | None = None
    collection: str | None = None
    media_count: int = 0


class AlbumCreate(BaseModel):
    """Request to create an album."""

    relative_path: str
    caption: str | None = None
    collection: str | None = None


class Tag(BaseModel):
    """Hierarchical tag."""

    id: int | None = None
    pid: int = 0  # parent id (0 = top-level)
    name: str
    children: list["Tag"] = Field(default_factory=list)
    media_count: int = 0


class ImageMetadata(BaseModel):
    """Camera and EXIF metadata (maps to ImageMetadata table)."""

    make: str | None = None
    model: str | None = None
    lens: str | None = None
    aperture: float | None = None
    focal_length: float | None = None
    focal_length_35: float | None = None
    exposure_time: float | None = None
    exposure_program: int | None = None
    exposure_mode: int | None = None
    sensitivity: int | None = None  # ISO
    flash: int | None = None
    white_balance: int | None = None
    metering_mode: int | None = None


class ImagePosition(BaseModel):
    """GPS position data."""

    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None


class MediaItem(BaseModel):
    """Media item in library (Digikam Images + ImageInformation joined)."""

    id: int
    name: str  # filename
    title: str = ""
    description: str = ""
    media_type: str = "image"  # "image" or "video"
    mime_type: str = ""
    album_id: int | None = None
    album_path: str | None = None
    storage_backend: str = "nas"
    storage_path: str | None = None  # relative path within backend
    file_size: int = 0
    unique_hash: str | None = None
    width: int | None = None
    height: int | None = None
    rating: int | None = None
    orientation: int | None = None
    format: str | None = None
    color_depth: int | None = None
    duration_seconds: float | None = None
    metadata: ImageMetadata = Field(default_factory=ImageMetadata)
    position: ImagePosition | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MediaUrl(BaseModel):
    """Permanent URL response for a media item."""

    url: str
    media_id: int
    filename: str
    width: int | None = None
    height: int | None = None


class MediaBatchItem(BaseModel):
    """Media item in batch response."""

    id: int
    title: str
    media_type: str
    url: str
    thumbnail_url: str
    tags: list[str] = Field(default_factory=list)
    width: int | None = None
    height: int | None = None


class MediaBatchResponse(BaseModel):
    """Batch media details response."""

    media: list[MediaBatchItem]


class CopyToRequest(BaseModel):
    """Request to copy media to another folder."""

    destination_folder: str


class CopyToResponse(BaseModel):
    """Response after copying media."""

    url: str
    path: str


class UploadResponse(BaseModel):
    """Upload response."""

    id: int
    title: str
    storage_path: str
    storage_backend: str
    file_size: int
    media_type: str
    created_at: datetime


class ImageComment(BaseModel):
    """Comment/annotation on a media item."""

    id: int | None = None
    imageid: int
    type: int = 1  # 1 = comment
    language: str | None = None
    author: str | None = None
    date: datetime | None = None
    comment: str


# -- Paper-reader integration --


class PaperCollection(BaseModel):
    """Paper collection linking Zotero article to album."""

    id: int | None = None
    zotero_key: str
    article_title: str
    album_id: int | None = None
    article_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaperFigure(BaseModel):
    """A single extracted figure from a paper."""

    figure_id: str
    label: str
    caption: str = ""
    native_url: str
    thumb_url: str | None = None


class PaperReaderPayload(BaseModel):
    """Payload from paper-reader when figures are extracted."""

    zotero_key: str
    article_title: str
    figures: list[PaperFigure]
    article_metadata: dict[str, Any] = Field(default_factory=dict)


# -- Scanner models (kept from v1) --


class ScanSource(BaseModel):
    """Scan source (Dropbox/local/SSH/NAS)."""

    id: int | None = None
    name: str
    source_type: str  # "dropbox", "local", "ssh", "nas"
    config: dict[str, Any]
    enabled: bool = True
    recursive: bool = True
    auto_tag: bool = True
    cron_schedule: str = "0 */6 * * *"
    last_scan_at: datetime | None = None
    last_scan_status: str | None = None


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


# -- Search --


class SearchQuery(BaseModel):
    """Search query parameters."""

    q: str = ""
    media_type: str | None = None
    album_id: int | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchResult(BaseModel):
    """Search result."""

    total: int
    items: list[MediaItem]


class TagSuggestion(BaseModel):
    """Tag suggestions for a media."""

    media_id: int
    suggested_tags: list[str]
    confidence: float | None = None


# -- Health --


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    db: str
    storage: str | None = None
    nas_mounted: bool | None = None


class InfoResponse(BaseModel):
    """Info endpoint response."""

    version: str = "2.0.0"
    total_media: int
    total_tags: int
    total_albums: int
    total_sources: int
    storage_backend: str
