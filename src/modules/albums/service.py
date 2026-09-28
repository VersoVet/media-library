"""Albums service - CRUD for Digikam Albums (collections/directories)."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiomysql

from src.config import get_storage_config
from src.database import execute, fetchall, fetchone, insert

logger = logging.getLogger(__name__)

# Default album root ID
DEFAULT_ALBUM_ROOT = 1


async def create_album(
    conn: aiomysql.Connection,
    relative_path: str,
    caption: str | None = None,
    album_root: int = DEFAULT_ALBUM_ROOT,
    create_on_disk: bool = True,
) -> int:
    """Create a new album (directory + DB entry).

    Args:
        conn: Database connection.
        relative_path: Path relative to album root (e.g., /papers/ABC123).
        caption: Album description.
        album_root: Album root ID.
        create_on_disk: Also create the directory on NAS.

    Returns:
        Album ID.
    """
    # Normalize path
    if not relative_path.startswith("/"):
        relative_path = f"/{relative_path}"

    # Check if already exists
    existing = await fetchone(
        conn,
        "SELECT id FROM Albums WHERE albumRoot = %s AND relativePath = %s",
        (album_root, relative_path),
    )
    if existing:
        return existing["id"]

    album_id = await insert(
        conn,
        "INSERT INTO Albums (albumRoot, relativePath, date, caption) VALUES (%s, %s, %s, %s)",
        (album_root, relative_path, datetime.now().date(), caption),
    )

    # Create directory on disk
    if create_on_disk:
        try:
            cfg = get_storage_config()
            nas_cfg = cfg.get("backends", {}).get("nas", {})
            mount_path = nas_cfg.get("mount_path", "/mnt/ml-store")
            base_dir = nas_cfg.get("base_dir", "media-library")
            dir_path = Path(mount_path) / base_dir / relative_path.lstrip("/")
            dir_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create album directory: {e}")

    logger.info(f"Created album {album_id}: {relative_path}")
    return album_id


async def get_album(conn: aiomysql.Connection, album_id: int) -> dict[str, Any] | None:
    """Get album by ID with media count.

    Args:
        conn: Database connection.
        album_id: Album ID.

    Returns:
        Album dict or None.
    """
    row = await fetchone(
        conn,
        """SELECT a.id, a.albumRoot, a.relativePath, a.date, a.caption, a.collection,
                  COUNT(i.id) as media_count
           FROM Albums a
           LEFT JOIN Images i ON i.album = a.id AND i.status = 1
           WHERE a.id = %s
           GROUP BY a.id""",
        (album_id,),
    )
    return dict(row) if row else None


async def list_albums(
    conn: aiomysql.Connection,
    parent_path: str | None = None,
    album_root: int = DEFAULT_ALBUM_ROOT,
) -> list[dict[str, Any]]:
    """List albums with media counts.

    Args:
        conn: Database connection.
        parent_path: Filter to children of this path.
        album_root: Album root ID.

    Returns:
        List of album dicts.
    """
    if parent_path is not None:
        # List direct children of parent_path
        if not parent_path.startswith("/"):
            parent_path = f"/{parent_path}"
        like_pattern = f"{parent_path.rstrip('/')}/%"
        rows = await fetchall(
            conn,
            """SELECT a.id, a.albumRoot, a.relativePath, a.date, a.caption,
                      COUNT(i.id) as media_count
               FROM Albums a
               LEFT JOIN Images i ON i.album = a.id AND i.status = 1
               WHERE a.albumRoot = %s AND a.relativePath LIKE %s
                 AND a.relativePath NOT LIKE %s
               GROUP BY a.id
               ORDER BY a.relativePath""",
            (album_root, like_pattern, f"{like_pattern}/%"),
        )
    else:
        rows = await fetchall(
            conn,
            """SELECT a.id, a.albumRoot, a.relativePath, a.date, a.caption,
                      COUNT(i.id) as media_count
               FROM Albums a
               LEFT JOIN Images i ON i.album = a.id AND i.status = 1
               WHERE a.albumRoot = %s
               GROUP BY a.id
               ORDER BY a.relativePath""",
            (album_root,),
        )

    return [dict(r) for r in rows]


async def update_album(conn: aiomysql.Connection, album_id: int, caption: str | None = None) -> bool:
    """Update album metadata.

    Args:
        conn: Database connection.
        album_id: Album ID.
        caption: New caption.

    Returns:
        True if updated.
    """
    if caption is not None:
        affected = await execute(conn, "UPDATE Albums SET caption = %s WHERE id = %s", (caption, album_id))
        return affected > 0
    return False


async def delete_album(conn: aiomysql.Connection, album_id: int) -> bool:
    """Delete album (does not delete media, just unlinks).

    Args:
        conn: Database connection.
        album_id: Album ID.

    Returns:
        True if deleted.
    """
    # Move images to root album
    await execute(conn, "UPDATE Images SET album = 1 WHERE album = %s", (album_id,))
    affected = await execute(conn, "DELETE FROM Albums WHERE id = %s", (album_id,))
    if affected > 0:
        logger.info(f"Deleted album {album_id}")
    return affected > 0


async def get_album_media(
    conn: aiomysql.Connection,
    album_id: int,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """List media in an album.

    Args:
        conn: Database connection.
        album_id: Album ID.
        limit: Max results.
        offset: Result offset.

    Returns:
        Tuple of (media list, total count).
    """
    from src.modules.search.service import _enrich_results

    count_row = await fetchone(conn, "SELECT COUNT(*) as cnt FROM Images WHERE album = %s AND status = 1", (album_id,))
    total = count_row["cnt"] if count_row else 0

    rows = await fetchall(
        conn,
        """SELECT i.id, i.album, i.name, i.category, i.fileSize, i.uniqueHash,
                  i.modificationDate,
                  ii.width, ii.height, ii.format, ii.rating, ii.creationDate,
                  a.relativePath as album_path
           FROM Images i
           LEFT JOIN ImageInformation ii ON i.id = ii.imageid
           LEFT JOIN Albums a ON i.album = a.id
           WHERE i.album = %s AND i.status = 1
           ORDER BY ii.creationDate DESC
           LIMIT %s OFFSET %s""",
        (album_id, limit, offset),
    )

    return await _enrich_results(conn, rows), total


async def add_media_to_album(conn: aiomysql.Connection, album_id: int, image_id: int) -> bool:
    """Move a media item to an album.

    Args:
        conn: Database connection.
        album_id: Target album ID.
        image_id: Image ID to move.

    Returns:
        True if updated.
    """
    affected = await execute(conn, "UPDATE Images SET album = %s WHERE id = %s", (album_id, image_id))
    return affected > 0
