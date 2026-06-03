# media-library - API Reference

**Base URL**: `http://{host}:8202`  
**Last Updated**: 2026-06-03

## Quick Links
- Health: `/health`
- OpenAPI docs: `/docs`
- Dashboard: `/static/` (static HTML)

---

## Core Endpoints

### Health & System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check (db, dropbox status) |
| GET | `/info` | Skill info (version, media count, tags count) |
| GET | `/` | Welcome message |

---

## Catalog (Media Management)

### Upload & CRUD
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/upload` | Upload media (multipart form: file, title, description, tags) |
| GET | `/api/media/{id}` | Get media details (metadata, tags) |
| DELETE | `/api/media/{id}` | Delete media |
| PUT | `/api/media/{id}/tags` | Update media tags (JSON: array of tag names) |
| GET | `/api/media/{id}/thumbnail` | Get thumbnail (webp) |

### Examples
```bash
# Upload image with tags
curl -X POST http://localhost:8202/api/upload \
  -F "file=@photo.jpg" \
  -F "title=Radiography - Dog Chest" \
  -F "description=Thoracic radiograph" \
  -F "tags=radiology,dog,thorax"

# Get media details
curl http://localhost:8202/api/media/123e4567-e89b-12d3-a456-426614174000

# Get thumbnail
curl http://localhost:8202/api/media/123e4567-e89b-12d3-a456-426614174000/thumbnail -o thumb.webp

# Update tags
curl -X PUT http://localhost:8202/api/media/123e4567-e89b-12d3-a456-426614174000/tags \
  -H "Content-Type: application/json" \
  -d '["radiology", "dog", "thorax", "urgent"]'

# Delete media
curl -X DELETE http://localhost:8202/api/media/123e4567-e89b-12d3-a456-426614174000
```

---

## Tagger (AI Tag Suggestions)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/media/{id}/suggest-tags` | Get tag suggestions from LLM vision |
| POST | `/api/media/{id}/apply-tags` | Apply suggested tags to media |

### Example
```bash
# Get tag suggestions for an image
curl -X POST http://localhost:8202/api/media/123e4567-e89b-12d3-a456-426614174000/suggest-tags

# Apply tags (body: JSON array of tag names)
curl -X POST http://localhost:8202/api/media/123e4567-e89b-12d3-a456-426614174000/apply-tags \
  -H "Content-Type: application/json" \
  -d '["dog", "radiology", "chest"]'
```

---

## Search & Navigation

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/search` | Full-text search or list all media if query empty |
| GET | `/api/tags` | List all tags with counts |
| GET | `/api/tags/{tag_name}/media` | Get media by tag |

### Query Parameters (for `/api/search`)
- `q` (optional, default ""): Search query. If empty, lists all media
- `media_type` (optional): 'image' or 'video'
- `limit` (optional, default 20): Max results
- `offset` (optional, default 0): Pagination offset

### Example
```bash
# Search for "radiography" images
curl "http://localhost:8202/api/search?q=radiography&media_type=image&limit=20"

# List all media (empty query)
curl "http://localhost:8202/api/search?limit=100"

# List all images only
curl "http://localhost:8202/api/search?media_type=image&limit=50"

# List all tags
curl http://localhost:8202/api/tags

# Get all videos tagged "surgery"
curl "http://localhost:8202/api/tags/surgery/media?media_type=video"
```

---

## Sources (Scan Configuration)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sources` | List all scan sources |
| POST | `/api/sources` | Create new scan source |
| GET | `/api/sources/{id}` | Get source details |
| PUT | `/api/sources/{id}` | Update source config |
| DELETE | `/api/sources/{id}` | Delete source |
| POST | `/api/sources/{id}/toggle` | Enable/disable source |
| GET | `/api/sources/{id}/logs` | Get scan logs for source (50 most recent) |

### Source Types & Config

**Dropbox:**
```json
{
  "name": "Dropbox Photos",
  "source_type": "dropbox",
  "config": {"path": "/Photos/"},
  "enabled": true,
  "recursive": true,
  "auto_tag": true,
  "cron_schedule": "0 */6 * * *"
}
```

**Local:**
```json
{
  "name": "Local Folder",
  "source_type": "local",
  "config": {"path": "/home/onyx/media/"},
  "enabled": true,
  "recursive": true,
  "auto_tag": true,
  "cron_schedule": "0 */6 * * *"
}
```

**SSH:**
```json
{
  "name": "Remote Server",
  "source_type": "ssh",
  "config": {
    "host": "10.0.0.X",
    "port": 22,
    "user": "onyx",
    "key": "ssh_key_axon",
    "path": "/data/photos/"
  },
  "enabled": true,
  "recursive": true,
  "auto_tag": false,
  "cron_schedule": "0 0 * * 0"
}
```

### Example
```bash
# List sources
curl http://localhost:8202/api/sources

# Create Dropbox source
curl -X POST http://localhost:8202/api/sources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Dropbox Backup",
    "source_type": "dropbox",
    "config": {"path": "/Backup/"},
    "enabled": true,
    "recursive": true,
    "auto_tag": true,
    "cron_schedule": "0 */6 * * *"
  }'

# Toggle source (enable/disable)
curl -X POST "http://localhost:8202/api/sources/1/toggle?enabled=false"

# Get scan logs for a source (50 most recent)
curl http://localhost:8202/api/sources/1/logs
```

---

## Scanner (Batch Import)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/scanner/run` | Scan all enabled sources |
| POST | `/api/scanner/run/{source_id}` | Scan specific source |

### Example
```bash
# Run all scans
curl -X POST http://localhost:8202/api/scanner/run

# Scan specific source
curl -X POST http://localhost:8202/api/scanner/run/1

# Response: SyncReport with files_found, files_imported, errors
```

---

## Deduplication & Quality Preservation

### Checksum System
Media files are automatically deduplicated using SHA256 file hashes:
- Each file is hashed upon import
- Hash is stored in `file_hash` field of media table
- Before importing, scanner checks if hash already exists
- Duplicates are skipped automatically and counted in `files_skipped`
- Works across all source types (Dropbox, Local, SSH)

### Quality Preservation
- **Original files**: Stored in full quality on Dropbox (`/media-library/{id}.{ext}`)
- **Thumbnails**: Generated in WebP format (quality=80) stored locally
- **Metadata**: EXIF data extracted and stored for images, ffprobe metadata for videos
- No lossy compression applied to originals

---

## Dashboard

Access the interactive dashboard at `/static/` with the following features:

### Library Tab
- **Search**: Full-text search by title, description, or tags
- **Filters**: Filter by media type (image/video) or specific tag
- **Tag Cloud**: Clickable tags showing media count
- **Thumbnails**: Preview images with fallback gradient background
- **Grid View**: Responsive media item grid with tag display

### Configuration Tab
- **Add/Edit Sources**: Create Dropbox, Local, or SSH scan sources
- **Source Management**: Enable/disable, delete sources
- **Cron Scheduling**: Set custom scan intervals (5-field cron)
- **Auto-Tag Toggle**: Enable/disable automatic tag suggestions per source

### Scan Logs Tab
- **Scan History**: View logs from all sources
- **Statistics**: Files found, imported, skipped per scan
- **Error Tracking**: View error messages for failed imports
- **Timeline**: Sorted by start time, newest first

---

## Response Models

### MediaItem
```json
{
  "id": "uuid",
  "title": "string",
  "description": "string",
  "media_type": "image|video",
  "mime_type": "string",
  "dropbox_path": "/media-library/...",
  "source_id": 1,
  "source_path": "...",
  "file_size": 12345,
  "file_hash": "sha256_hash_hex_string",
  "metadata": {
    "width": 1920,
    "height": 1080,
    "duration_seconds": null,
    "exif": {}
  },
  "tags": ["tag1", "tag2"],
  "created_at": "2026-01-01T12:00:00Z",
  "updated_at": "2026-01-01T12:00:00Z"
}
```

### SearchResult
```json
{
  "total": 100,
  "items": [
    { ... MediaItem ... }
  ]
}
```

### SyncReport
```json
{
  "source_id": 1,
  "files_found": 50,
  "files_imported": 45,
  "files_skipped": 5,
  "errors": ["filename: error message"],
  "duration_seconds": 123.45
}
```

### ScanLog
```json
{
  "id": 1,
  "source_id": 1,
  "started_at": "2026-01-01T12:00:00",
  "finished_at": "2026-01-01T12:05:30",
  "files_found": 50,
  "files_imported": 45,
  "files_skipped": 5,
  "errors": [
    "photo001.jpg: File not found",
    "photo002.jpg: Invalid format"
  ]
}
```

---

## Error Handling

All endpoints return standard HTTP status codes:
- `200 OK`: Success
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

Error response format:
```json
{
  "detail": "Error message here"
}
```

---

## Authentication

Currently no authentication. In production, add API key or JWT token to requests.
