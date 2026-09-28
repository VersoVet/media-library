"""Catalog service for media CRUD operations (Digikam-compatible)."""

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

import aiomysql

from src.database import (
    IMAGE_CATEGORY_IMAGE,
    IMAGE_CATEGORY_VIDEO,
    IMAGE_STATUS_REMOVED,
    IMAGE_STATUS_VISIBLE,
    execute,
    fetchall,
    fetchone,
    insert,
)

logger = logging.getLogger(__name__)


def calculate_file_hash(file_bytes: bytes) -> str:
    """Calculate SHA256 hash of file bytes.

    Args:
        file_bytes: File content.

    Returns:
        SHA256 hex digest.
    """
    return hashlib.sha256(file_bytes).hexdigest()


async def create_media(
    conn: aiomysql.Connection,
    name: str,
    title: str,
    description: str,
    media_type: str,
    mime_type: str,
    album_id: int,
    storage_backend: str,
    storage_path: str,
    file_size: int,
    metadata: dict[str, Any],
    source_id: int | None = None,
    source_path: str | None = None,
    tags: list[str] | None = None,
    file_hash: str | None = None,
) -> int:
    """Create new media entry in Digikam database.

    Inserts into Images, ImageInformation, and optionally ImageMetadata.

    Args:
        conn: Database connection.
        name: Filename.
        title: Media title.
        description: Media description.
        media_type: 'image' or 'video'.
        mime_type: MIME type.
        album_id: Album ID in Digikam.
        storage_backend: Storage backend name ('nas' or 'dropbox').
        storage_path: Relative path in storage backend.
        file_size: File size in bytes.
        metadata: Extracted metadata dict.
        source_id: Source ID if imported.
        source_path: Path in source.
        tags: List of tag names.
        file_hash: SHA256 hash for deduplication.

    Returns:
        Image ID (Digikam auto-increment).
    """
    if media_type not in ("image", "video"):
        raise ValueError(f"Invalid media_type: {media_type}. Must be 'image' or 'video'.")

    now = datetime.now(UTC)
    category = IMAGE_CATEGORY_IMAGE if media_type == "image" else IMAGE_CATEGORY_VIDEO

    # Insert into Images table
    image_id = await insert(
        conn,
        """INSERT INTO Images (album, name, status, category, modificationDate, fileSize, uniqueHash)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (album_id, name, IMAGE_STATUS_VISIBLE, category, now, file_size, file_hash),
    )

    # Insert into ImageInformation
    fmt = metadata.get("format", mime_type.split("/")[-1])
    await execute(
        conn,
        """INSERT INTO ImageInformation (imageid, creationDate, digitizationDate, width, height, format, colorDepth)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (image_id, now, now, metadata.get("width"), metadata.get("height"), fmt, metadata.get("color_depth")),
    )

    # Insert into ImageMetadata if EXIF data present
    exif = metadata.get("exif", {})
    if exif:
        await execute(
            conn,
            """INSERT INTO ImageMetadata (imageid, make, model, lens, aperture, focalLength,
               exposureTime, sensitivity)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                image_id,
                exif.get("make"),
                exif.get("model"),
                exif.get("lens"),
                exif.get("aperture"),
                exif.get("focal_length"),
                exif.get("exposure_time"),
                exif.get("iso"),
            ),
        )

    # Store media-library specific properties (storage_backend, storage_path, source info)
    props = [
        (image_id, "ml:storage_backend", storage_backend),
        (image_id, "ml:storage_path", storage_path),
        (image_id, "ml:title", title),
        (image_id, "ml:mime_type", mime_type),
    ]
    if description:
        props.append((image_id, "ml:description", description))
    if source_id is not None:
        props.append((image_id, "ml:source_id", str(source_id)))
    if source_path:
        props.append((image_id, "ml:source_path", source_path))

    for prop in props:
        await execute(
            conn,
            "INSERT INTO ImageProperties (imageid, property, value) VALUES (%s, %s, %s)",
            prop,
        )

    # Add title as ImageComment (Digikam convention)
    if title:
        await execute(
            conn,
            """INSERT INTO ImageComments (imageid, type, language, author, date, comment)
               VALUES (%s, 3, 'x-default', 'media-library', %s, %s)""",
            (image_id, now, title),
        )

    # Add tags
    if tags:
        for tag_name in tags:
            await add_tag_to_media(conn, image_id, tag_name)

    logger.info(f"Created media {image_id}: {name} (album={album_id}, backend={storage_backend})")
    return image_id


async def get_media(conn: aiomysql.Connection, image_id: int) -> dict[str, Any] | None:
    """Get media by ID with all joined data.

    Args:
        conn: Database connection.
        image_id: Digikam image ID.

    Returns:
        Media dict with tags, properties, or None if not found.
    """
    row = await fetchone(
        conn,
        """SELECT i.id, i.album, i.name, i.status, i.category, i.modificationDate,
                  i.fileSize, i.uniqueHash,
                  ii.width, ii.height, ii.format, ii.rating, ii.orientation,
                  ii.creationDate, ii.colorDepth,
                  a.relativePath as album_path
           FROM Images i
           LEFT JOIN ImageInformation ii ON i.id = ii.imageid
           LEFT JOIN Albums a ON i.album = a.id
           WHERE i.id = %s AND i.status = %s""",
        (image_id, IMAGE_STATUS_VISIBLE),
    )
    if not row:
        return None

    media = dict(row)

    # Fetch ml: properties
    props = await fetchall(
        conn,
        "SELECT property, value FROM ImageProperties WHERE imageid = %s AND property LIKE 'ml:%%'",
        (image_id,),
    )
    for p in props:
        key = p["property"].replace("ml:", "")
        media[key] = p["value"]

    # Fetch tags
    tags = await fetchall(
        conn,
        """SELECT t.name FROM Tags t
           JOIN ImageTags it ON t.id = it.tagid
           WHERE it.imageid = %s AND t.pid >= 0""",
        (image_id,),
    )
    media["tags"] = [t["name"] for t in tags]

    return media


async def list_media(
    conn: aiomysql.Connection,
    album_id: int | None = None,
    media_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """List media with pagination.

    Args:
        conn: Database connection.
        album_id: Filter by album.
        media_type: Filter by 'image' or 'video'.
        limit: Max items per page.
        offset: Page offset.

    Returns:
        Tuple of (media list, total count).
    """
    where_parts = ["i.status = %s"]
    params: list[Any] = [IMAGE_STATUS_VISIBLE]

    if album_id is not None:
        where_parts.append("i.album = %s")
        params.append(album_id)
    if media_type:
        cat = IMAGE_CATEGORY_IMAGE if media_type == "image" else IMAGE_CATEGORY_VIDEO
        where_parts.append("i.category = %s")
        params.append(cat)

    where_sql = " AND ".join(where_parts)

    # Count
    count_row = await fetchone(conn, f"SELECT COUNT(*) as cnt FROM Images i WHERE {where_sql}", tuple(params))
    total = count_row["cnt"] if count_row else 0

    # Fetch
    rows = await fetchall(
        conn,
        f"""SELECT i.id, i.album, i.name, i.category, i.fileSize, i.uniqueHash,
                   ii.width, ii.height, ii.format, ii.rating, ii.creationDate,
                   a.relativePath as album_path
            FROM Images i
            LEFT JOIN ImageInformation ii ON i.id = ii.imageid
            LEFT JOIN Albums a ON i.album = a.id
            WHERE {where_sql}
            ORDER BY ii.creationDate DESC
            LIMIT %s OFFSET %s""",
        tuple(params) + (limit, offset),
    )

    results = []
    for row in rows:
        media = dict(row)
        # Fetch properties
        props = await fetchall(
            conn,
            "SELECT property, value FROM ImageProperties WHERE imageid = %s AND property LIKE 'ml:%%'",
            (media["id"],),
        )
        for p in props:
            media[p["property"].replace("ml:", "")] = p["value"]
        # Fetch tags
        tags = await fetchall(
            conn,
            "SELECT t.name FROM Tags t JOIN ImageTags it ON t.id = it.tagid WHERE it.imageid = %s AND t.pid >= 0",
            (media["id"],),
        )
        media["tags"] = [t["name"] for t in tags]
        results.append(media)

    return results, total


async def delete_media(conn: aiomysql.Connection, image_id: int) -> bool:
    """Delete media by ID (mark as removed in Digikam).

    Args:
        conn: Database connection.
        image_id: Image ID.

    Returns:
        True if deleted.
    """
    affected = await execute(conn, "UPDATE Images SET status = %s WHERE id = %s", (IMAGE_STATUS_REMOVED, image_id))
    if affected > 0:
        logger.info(f"Deleted media {image_id}")
    return affected > 0


async def update_tags(conn: aiomysql.Connection, image_id: int, tags: list[str]) -> None:
    """Replace media tags.

    Args:
        conn: Database connection.
        image_id: Image ID.
        tags: New list of tag names.

    Raises:
        ValueError: If media not found.
    """
    row = await fetchone(conn, "SELECT id FROM Images WHERE id = %s", (image_id,))
    if not row:
        raise ValueError(f"Media {image_id} not found")

    await execute(conn, "DELETE FROM ImageTags WHERE imageid = %s", (image_id,))

    for tag_name in tags:
        await add_tag_to_media(conn, image_id, tag_name)

    logger.info(f"Updated tags for media {image_id}: {tags}")


async def add_tag_to_media(conn: aiomysql.Connection, image_id: int, tag_name: str) -> None:
    """Add a tag to media (create tag if not exists).

    Args:
        conn: Database connection.
        image_id: Image ID.
        tag_name: Tag name.
    """
    tag_row = await fetchone(conn, "SELECT id FROM Tags WHERE name = %s AND pid >= 0", (tag_name,))
    if tag_row:
        tag_id = tag_row["id"]
    else:
        tag_id = await insert(conn, "INSERT INTO Tags (pid, name) VALUES (0, %s)", (tag_name,))

    try:
        await execute(conn, "INSERT IGNORE INTO ImageTags (imageid, tagid) VALUES (%s, %s)", (image_id, tag_id))
    except Exception:
        pass  # Duplicate


async def get_all_tags(conn: aiomysql.Connection) -> list[dict[str, Any]]:
    """Get all tags with media count.

    Args:
        conn: Database connection.

    Returns:
        List of tag dicts with id, name, count.
    """
    return await fetchall(
        conn,
        """SELECT t.id, t.name, t.pid, COUNT(it.imageid) as count
           FROM Tags t
           LEFT JOIN ImageTags it ON t.id = it.tagid
           WHERE t.pid >= 0
           GROUP BY t.id, t.name, t.pid
           ORDER BY count DESC""",
    )
