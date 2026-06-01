"""Catalog service for media CRUD operations."""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


async def generate_media_id() -> str:
    """Generate unique media ID.

    Returns:
        UUID4 string.
    """
    return str(uuid.uuid4())


async def create_media(
    db: aiosqlite.Connection,
    title: str,
    description: str,
    media_type: str,
    mime_type: str,
    dropbox_path: str,
    file_size: int,
    metadata: dict[str, Any],
    source_id: int | None = None,
    source_path: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Create new media entry in database.

    Args:
        db: Database connection.
        title: Media title.
        description: Media description.
        media_type: 'image' or 'video'.
        mime_type: MIME type.
        dropbox_path: Path in Dropbox.
        file_size: File size in bytes.
        metadata: Extracted metadata dict.
        source_id: Source ID if imported from a source.
        source_path: Path in source.
        tags: List of tags.

    Returns:
        Media ID.

    Raises:
        Exception: If database operation fails.
    """
    media_id = await generate_media_id()
    now = datetime.now(UTC).isoformat()

    # Convert metadata dict to JSON
    metadata_json = json.dumps(metadata)

    await db.execute(
        """
        INSERT INTO media (
            id, title, description, media_type, mime_type,
            dropbox_path, source_id, source_path, file_size,
            width, height, duration_seconds, metadata_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            media_id,
            title,
            description,
            media_type,
            mime_type,
            dropbox_path,
            source_id,
            source_path,
            file_size,
            metadata.get("width"),
            metadata.get("height"),
            metadata.get("duration_seconds"),
            metadata_json,
            now,
            now,
        ),
    )

    # Add tags if provided
    if tags:
        for tag_name in tags:
            await add_tag_to_media(db, media_id, tag_name)

    await db.commit()
    logger.info(f"Created media {media_id}: {title}")
    return media_id


async def get_media(db: aiosqlite.Connection, media_id: str) -> dict[str, Any] | None:
    """Get media by ID with tags.

    Args:
        db: Database connection.
        media_id: Media ID.

    Returns:
        Media dict with tags list, or None if not found.
    """
    cursor = await db.execute(
        "SELECT * FROM media WHERE id = ?",
        (media_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None

    media = dict(row)
    media["metadata"] = json.loads(media.get("metadata_json", "{}"))
    del media["metadata_json"]

    # Fetch tags
    tags_cursor = await db.execute(
        """
        SELECT t.name FROM tags t
        JOIN media_tags mt ON t.id = mt.tag_id
        WHERE mt.media_id = ?
        """,
        (media_id,),
    )
    tags_rows = await tags_cursor.fetchall()
    media["tags"] = [dict(r)["name"] for r in tags_rows]

    return media


async def list_media(
    db: aiosqlite.Connection,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """List all media with pagination.

    Args:
        db: Database connection.
        limit: Max items per page.
        offset: Page offset.

    Returns:
        Tuple of (media list, total count).
    """
    # Get total count
    count_cursor = await db.execute("SELECT COUNT(*) as cnt FROM media")
    count_row = await count_cursor.fetchone()
    total = dict(count_row)["cnt"] if count_row else 0

    # Fetch page
    cursor = await db.execute(
        "SELECT * FROM media ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()

    media_list = []
    for row in rows:
        media = dict(row)
        media["metadata"] = json.loads(media.get("metadata_json", "{}"))
        del media["metadata_json"]

        # Fetch tags
        tags_cursor = await db.execute(
            """
            SELECT t.name FROM tags t
            JOIN media_tags mt ON t.id = mt.tag_id
            WHERE mt.media_id = ?
            """,
            (media["id"],),
        )
        tags_rows = await tags_cursor.fetchall()
        media["tags"] = [dict(r)["name"] for r in tags_rows]
        media_list.append(media)

    return media_list, total


async def delete_media(db: aiosqlite.Connection, media_id: str) -> bool:
    """Delete media by ID (cascades to tags).

    Args:
        db: Database connection.
        media_id: Media ID.

    Returns:
        True if deleted, False if not found.
    """
    cursor = await db.execute(
        "DELETE FROM media WHERE id = ?",
        (media_id,),
    )
    await db.commit()
    return cursor.rowcount > 0


async def update_tags(
    db: aiosqlite.Connection,
    media_id: str,
    tags: list[str],
) -> None:
    """Replace media tags.

    Args:
        db: Database connection.
        media_id: Media ID.
        tags: New list of tag names.

    Raises:
        Exception: If media not found or database operation fails.
    """
    # Verify media exists
    cursor = await db.execute("SELECT id FROM media WHERE id = ?", (media_id,))
    if not await cursor.fetchone():
        raise ValueError(f"Media {media_id} not found")

    # Remove existing tags
    await db.execute("DELETE FROM media_tags WHERE media_id = ?", (media_id,))

    # Add new tags
    for tag_name in tags:
        await add_tag_to_media(db, media_id, tag_name)

    await db.commit()
    logger.info(f"Updated tags for media {media_id}")


async def add_tag_to_media(db: aiosqlite.Connection, media_id: str, tag_name: str) -> None:
    """Add a tag to a media (create tag if not exists).

    Args:
        db: Database connection.
        media_id: Media ID.
        tag_name: Tag name.
    """
    # Get or create tag
    cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    tag_row = await cursor.fetchone()
    if tag_row:
        tag_id = dict(tag_row)["id"]
    else:
        await db.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
        await db.commit()
        cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        tag_row = await cursor.fetchone()
        if tag_row:
            tag_id = dict(tag_row)["id"]
        else:
            raise ValueError(f"Failed to create tag: {tag_name}")

    # Add media-tag relationship
    try:
        await db.execute(
            "INSERT INTO media_tags (media_id, tag_id) VALUES (?, ?)",
            (media_id, tag_id),
        )
    except Exception:
        pass  # Ignore duplicates


async def get_all_tags(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    """Get all tags with media count.

    Args:
        db: Database connection.

    Returns:
        List of tag dicts with id, name, count.
    """
    cursor = await db.execute(
        """
        SELECT t.id, t.name, COUNT(mt.media_id) as count
        FROM tags t
        LEFT JOIN media_tags mt ON t.id = mt.tag_id
        GROUP BY t.id, t.name
        ORDER BY t.name
        """,
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
