"""Search service using MariaDB (Digikam-compatible)."""

import logging
from typing import Any

import aiomysql

from src.database import IMAGE_CATEGORY_IMAGE, IMAGE_CATEGORY_VIDEO, IMAGE_STATUS_VISIBLE, fetchall, fetchone

logger = logging.getLogger(__name__)


async def list_all_media(
    conn: aiomysql.Connection,
    media_type: str | None = None,
    album_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """List all media with optional filtering.

    Args:
        conn: Database connection.
        media_type: Filter by 'image' or 'video'.
        album_id: Filter by album.
        limit: Max results.
        offset: Result offset.

    Returns:
        Tuple of (media list, total count).
    """
    where_parts = ["i.status = %s"]
    params: list[Any] = [IMAGE_STATUS_VISIBLE]

    if media_type:
        cat = IMAGE_CATEGORY_IMAGE if media_type == "image" else IMAGE_CATEGORY_VIDEO
        where_parts.append("i.category = %s")
        params.append(cat)
    if album_id is not None:
        where_parts.append("i.album = %s")
        params.append(album_id)

    where_sql = " AND ".join(where_parts)

    count_row = await fetchone(conn, f"SELECT COUNT(*) as cnt FROM Images i WHERE {where_sql}", tuple(params))
    total = count_row["cnt"] if count_row else 0

    rows = await fetchall(
        conn,
        f"""SELECT i.id, i.album, i.name, i.category, i.fileSize, i.uniqueHash,
                   i.modificationDate,
                   ii.width, ii.height, ii.format, ii.rating, ii.creationDate,
                   a.relativePath as album_path
            FROM Images i
            LEFT JOIN ImageInformation ii ON i.id = ii.imageid
            LEFT JOIN Albums a ON i.album = a.id
            WHERE {where_sql}
            ORDER BY COALESCE(ii.creationDate, i.modificationDate) DESC
            LIMIT %s OFFSET %s""",
        tuple(params) + (limit, offset),
    )

    return await _enrich_results(conn, rows), total


async def search(
    conn: aiomysql.Connection,
    query: str,
    media_type: str | None = None,
    album_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Search media by name, title, tags, or description.

    Uses LIKE queries on name + ImageProperties + Tags.

    Args:
        conn: Database connection.
        query: Search query string.
        media_type: Filter by 'image' or 'video'.
        album_id: Filter by album.
        limit: Max results.
        offset: Result offset.

    Returns:
        Tuple of (results list, total count).
    """
    like_query = f"%{query}%"
    where_parts = ["i.status = %s"]
    params: list[Any] = [IMAGE_STATUS_VISIBLE]

    if media_type:
        cat = IMAGE_CATEGORY_IMAGE if media_type == "image" else IMAGE_CATEGORY_VIDEO
        where_parts.append("i.category = %s")
        params.append(cat)
    if album_id is not None:
        where_parts.append("i.album = %s")
        params.append(album_id)

    where_sql = " AND ".join(where_parts)

    # Search across name, title (ImageProperties), tags, and comments
    search_sql = f"""
        SELECT DISTINCT i.id, i.album, i.name, i.category, i.fileSize, i.uniqueHash,
               i.modificationDate,
               ii.width, ii.height, ii.format, ii.rating, ii.creationDate,
               a.relativePath as album_path
        FROM Images i
        LEFT JOIN ImageInformation ii ON i.id = ii.imageid
        LEFT JOIN Albums a ON i.album = a.id
        LEFT JOIN ImageProperties ip ON i.id = ip.imageid
        LEFT JOIN ImageTags it ON i.id = it.imageid
        LEFT JOIN Tags t ON it.tagid = t.id
        LEFT JOIN ImageComments ic ON i.id = ic.imageid
        WHERE {where_sql}
          AND (i.name LIKE %s
               OR ip.value LIKE %s
               OR t.name LIKE %s
               OR ic.comment LIKE %s)
        ORDER BY COALESCE(ii.creationDate, i.modificationDate) DESC
    """

    # Count
    count_sql = f"""
        SELECT COUNT(DISTINCT i.id) as cnt
        FROM Images i
        LEFT JOIN ImageProperties ip ON i.id = ip.imageid
        LEFT JOIN ImageTags it ON i.id = it.imageid
        LEFT JOIN Tags t ON it.tagid = t.id
        LEFT JOIN ImageComments ic ON i.id = ic.imageid
        WHERE {where_sql}
          AND (i.name LIKE %s OR ip.value LIKE %s OR t.name LIKE %s OR ic.comment LIKE %s)
    """
    count_params = tuple(params) + (like_query, like_query, like_query, like_query)
    count_row = await fetchone(conn, count_sql, count_params)
    total = count_row["cnt"] if count_row else 0

    search_params = tuple(params) + (like_query, like_query, like_query, like_query, limit, offset)
    rows = await fetchall(conn, search_sql + " LIMIT %s OFFSET %s", search_params)

    return await _enrich_results(conn, rows), total


async def get_all_tags(conn: aiomysql.Connection) -> list[dict[str, Any]]:
    """Get all tags with media count.

    Args:
        conn: Database connection.

    Returns:
        List of tag dicts with id, name, pid, count.
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


async def get_media_by_tag(
    conn: aiomysql.Connection,
    tag_name: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Get media for a specific tag.

    Args:
        conn: Database connection.
        tag_name: Tag name.
        limit: Max results.
        offset: Result offset.

    Returns:
        Tuple of (media list, total count).
    """
    count_row = await fetchone(
        conn,
        """SELECT COUNT(DISTINCT it.imageid) as cnt
           FROM ImageTags it JOIN Tags t ON it.tagid = t.id
           JOIN Images i ON it.imageid = i.id
           WHERE t.name = %s AND i.status = %s""",
        (tag_name, IMAGE_STATUS_VISIBLE),
    )
    total = count_row["cnt"] if count_row else 0

    rows = await fetchall(
        conn,
        """SELECT DISTINCT i.id, i.album, i.name, i.category, i.fileSize, i.uniqueHash,
                  i.modificationDate,
                  ii.width, ii.height, ii.format, ii.rating, ii.creationDate,
                  a.relativePath as album_path
           FROM Images i
           JOIN ImageTags it ON i.id = it.imageid
           JOIN Tags t ON it.tagid = t.id
           LEFT JOIN ImageInformation ii ON i.id = ii.imageid
           LEFT JOIN Albums a ON i.album = a.id
           WHERE t.name = %s AND i.status = %s
           ORDER BY COALESCE(ii.creationDate, i.modificationDate) DESC
           LIMIT %s OFFSET %s""",
        (tag_name, IMAGE_STATUS_VISIBLE, limit, offset),
    )

    return await _enrich_results(conn, rows), total


async def _enrich_results(
    conn: aiomysql.Connection,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enrich image rows with properties and tags.

    Args:
        conn: Database connection.
        rows: Raw image rows from query.

    Returns:
        Enriched media dicts.
    """
    results = []
    for row in rows:
        media = dict(row)
        img_id = media["id"]

        # Fetch ml: properties
        props = await fetchall(
            conn,
            "SELECT property, value FROM ImageProperties WHERE imageid = %s AND property LIKE 'ml:%%'",
            (img_id,),
        )
        for p in props:
            media[p["property"].replace("ml:", "")] = p["value"]

        # Fetch tags
        tags = await fetchall(
            conn,
            "SELECT t.name FROM Tags t JOIN ImageTags it ON t.id = it.tagid WHERE it.imageid = %s AND t.pid >= 0",
            (img_id,),
        )
        media["tags"] = [t["name"] for t in tags]
        results.append(media)

    return results
