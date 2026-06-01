"""Full-text search service using SQLite FTS5."""

import json
import logging
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


async def list_all_media(
    db: aiosqlite.Connection,
    media_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """List all media with optional filtering.

    Args:
        db: Database connection.
        media_type: Filter by 'image' or 'video' (optional).
        limit: Max results.
        offset: Result offset.

    Returns:
        Tuple of (media list, total count).
    """
    # Build WHERE clause
    where_sql = ""
    params: list[Any] = []

    if media_type:
        where_sql = "WHERE media_type = ?"
        params.append(media_type)

    # Count total
    count_sql = f"SELECT COUNT(*) as cnt FROM media {where_sql}"
    count_cursor = await db.execute(count_sql, params)
    count_row = await count_cursor.fetchone()
    total = dict(count_row)["cnt"] if count_row else 0

    # Fetch results
    results_sql = f"""
        SELECT *
        FROM media
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """
    results_params = params + [limit, offset]

    cursor = await db.execute(results_sql, results_params)
    rows = await cursor.fetchall()

    # Convert to dicts and fetch tags
    results = []
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
        results.append(media)

    logger.info(f"Listed {len(results)} media items (total: {total})")
    return results, total


async def search(
    db: aiosqlite.Connection,
    query: str,
    media_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Search media using FTS5.

    Args:
        db: Database connection.
        query: Search query string.
        media_type: Filter by 'image' or 'video' (optional).
        limit: Max results.
        offset: Result offset.

    Returns:
        Tuple of (results list, total count).
    """
    # Build FTS5 query
    fts_query = query.replace('"', '""')  # Escape quotes

    # Build WHERE clause
    where_parts = []
    params: list[Any] = []

    if media_type:
        where_parts.append("m.media_type = ?")
        params.append(media_type)

    # Search FTS5 table, join back to media
    where_sql = " AND " + " AND ".join(where_parts) if where_parts else ""

    # First, count total
    count_sql = f"""
        SELECT COUNT(DISTINCT m.id) as cnt
        FROM media_fts f
        JOIN media m ON f.rowid = m.rowid
        WHERE media_fts MATCH ?
        {where_sql}
    """
    count_params = [fts_query] + params

    count_cursor = await db.execute(count_sql, count_params)
    count_row = await count_cursor.fetchone()
    total = dict(count_row)["cnt"] if count_row else 0

    # Fetch results
    results_sql = f"""
        SELECT DISTINCT m.*
        FROM media_fts f
        JOIN media m ON f.rowid = m.rowid
        WHERE media_fts MATCH ?
        {where_sql}
        ORDER BY m.created_at DESC
        LIMIT ? OFFSET ?
    """
    results_params = [fts_query] + params + [limit, offset]

    cursor = await db.execute(results_sql, results_params)
    rows = await cursor.fetchall()

    # Convert to dicts and fetch tags
    results = []
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
        results.append(media)

    logger.info(f"Search query '{query}': {len(results)} results (total: {total})")
    return results, total


async def update_fts_index(db: aiosqlite.Connection, media_id: str) -> None:
    """Update FTS5 index for a media item.

    Args:
        db: Database connection.
        media_id: Media ID.
    """
    # Get media with tags
    cursor = await db.execute(
        """
        SELECT m.title, m.description, GROUP_CONCAT(t.name, ' ') as tags
        FROM media m
        LEFT JOIN media_tags mt ON m.id = mt.media_id
        LEFT JOIN tags t ON mt.tag_id = t.id
        WHERE m.id = ?
        GROUP BY m.id
        """,
        (media_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return

    row_dict = dict(row)
    title = row_dict.get("title", "")
    description = row_dict.get("description", "")
    tags = row_dict.get("tags", "")

    # Delete old index entry
    await db.execute("DELETE FROM media_fts WHERE rowid = (SELECT rowid FROM media WHERE id = ?)", (media_id,))

    # Insert new index entry
    await db.execute(
        """
        INSERT INTO media_fts (rowid, title, description, tags)
        SELECT rowid, ?, ?, ?
        FROM media
        WHERE id = ?
        """,
        (title, description, tags, media_id),
    )
    await db.commit()


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
        ORDER BY COUNT(mt.media_id) DESC
        """
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_media_by_tag(
    db: aiosqlite.Connection,
    tag_name: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Get media for a specific tag.

    Args:
        db: Database connection.
        tag_name: Tag name.
        limit: Max results.
        offset: Result offset.

    Returns:
        Tuple of (media list, total count).
    """
    # Count total
    count_cursor = await db.execute(
        """
        SELECT COUNT(DISTINCT mt.media_id) as cnt
        FROM media_tags mt
        JOIN tags t ON mt.tag_id = t.id
        WHERE t.name = ?
        """,
        (tag_name,),
    )
    count_row = await count_cursor.fetchone()
    total = dict(count_row)["cnt"] if count_row else 0

    # Fetch media
    cursor = await db.execute(
        """
        SELECT DISTINCT m.*
        FROM media m
        JOIN media_tags mt ON m.id = mt.media_id
        JOIN tags t ON mt.tag_id = t.id
        WHERE t.name = ?
        ORDER BY m.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (tag_name, limit, offset),
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
