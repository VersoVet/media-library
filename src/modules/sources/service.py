"""Source management service for scan configuration."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


async def create_source(
    db: aiosqlite.Connection,
    name: str,
    source_type: str,
    config: dict[str, Any],
    enabled: bool = True,
    recursive: bool = True,
    auto_tag: bool = True,
    cron_schedule: str = "0 */6 * * *",
) -> int:
    """Create a new scan source.

    Args:
        db: Database connection.
        name: Source name (display label).
        source_type: Type ('dropbox', 'local', 'ssh').
        config: Source configuration dict (type-specific).
        enabled: Whether source is enabled.
        recursive: Scan subfolders.
        auto_tag: Suggest tags for new imports.
        cron_schedule: Cron expression for automatic scans.

    Returns:
        Source ID.

    Raises:
        ValueError: If source_type invalid.
    """
    if source_type not in ("dropbox", "local", "ssh"):
        raise ValueError(f"Invalid source_type: {source_type}")

    config_json = json.dumps(config)

    await db.execute(
        """
        INSERT INTO scan_sources (
            name, source_type, config_json, enabled, recursive,
            auto_tag, cron_schedule
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (name, source_type, config_json, int(enabled), int(recursive), int(auto_tag), cron_schedule),
    )
    await db.commit()

    # Get inserted ID
    cursor = await db.execute("SELECT last_insert_rowid() as id")
    row = await cursor.fetchone()
    source_id = dict(row)["id"] if row else 0

    logger.info(f"Created scan source {source_id}: {name}")
    return source_id


async def get_source(db: aiosqlite.Connection, source_id: int) -> dict[str, Any] | None:
    """Get source by ID.

    Args:
        db: Database connection.
        source_id: Source ID.

    Returns:
        Source dict with parsed config, or None if not found.
    """
    cursor = await db.execute("SELECT * FROM scan_sources WHERE id = ?", (source_id,))
    row = await cursor.fetchone()
    if not row:
        return None

    source = dict(row)
    source["config"] = json.loads(source.get("config_json", "{}"))
    del source["config_json"]
    source["enabled"] = bool(source.get("enabled", 0))
    source["recursive"] = bool(source.get("recursive", 0))
    source["auto_tag"] = bool(source.get("auto_tag", 0))

    return source


async def list_sources(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    """List all scan sources.

    Args:
        db: Database connection.

    Returns:
        List of source dicts.
    """
    cursor = await db.execute("SELECT * FROM scan_sources ORDER BY name")
    rows = await cursor.fetchall()

    sources = []
    for row in rows:
        source = dict(row)
        source["config"] = json.loads(source.get("config_json", "{}"))
        del source["config_json"]
        source["enabled"] = bool(source.get("enabled", 0))
        source["recursive"] = bool(source.get("recursive", 0))
        source["auto_tag"] = bool(source.get("auto_tag", 0))
        sources.append(source)

    return sources


async def update_source(
    db: aiosqlite.Connection,
    source_id: int,
    **kwargs: Any,
) -> bool:
    """Update source fields.

    Args:
        db: Database connection.
        source_id: Source ID.
        **kwargs: Fields to update (name, config, enabled, recursive, etc.).

    Returns:
        True if updated, False if not found.
    """
    # Prepare update statement
    updates = []
    values = []

    if "name" in kwargs:
        updates.append("name = ?")
        values.append(kwargs["name"])

    if "config" in kwargs:
        updates.append("config_json = ?")
        values.append(json.dumps(kwargs["config"]))

    if "enabled" in kwargs:
        updates.append("enabled = ?")
        values.append(int(kwargs["enabled"]))

    if "recursive" in kwargs:
        updates.append("recursive = ?")
        values.append(int(kwargs["recursive"]))

    if "auto_tag" in kwargs:
        updates.append("auto_tag = ?")
        values.append(int(kwargs["auto_tag"]))

    if "cron_schedule" in kwargs:
        updates.append("cron_schedule = ?")
        values.append(kwargs["cron_schedule"])

    if not updates:
        return False

    values.append(source_id)
    sql = f"UPDATE scan_sources SET {', '.join(updates)} WHERE id = ?"

    cursor = await db.execute(sql, values)
    await db.commit()

    if cursor.rowcount > 0:
        logger.info(f"Updated scan source {source_id}")
        return True

    return False


async def delete_source(db: aiosqlite.Connection, source_id: int) -> bool:
    """Delete source by ID.

    Args:
        db: Database connection.
        source_id: Source ID.

    Returns:
        True if deleted, False if not found.
    """
    cursor = await db.execute("DELETE FROM scan_sources WHERE id = ?", (source_id,))
    await db.commit()

    if cursor.rowcount > 0:
        logger.info(f"Deleted scan source {source_id}")
        return True

    return False


async def toggle_source(db: aiosqlite.Connection, source_id: int, enabled: bool) -> bool:
    """Enable or disable a source.

    Args:
        db: Database connection.
        source_id: Source ID.
        enabled: New enabled state.

    Returns:
        True if updated, False if not found.
    """
    return await update_source(db, source_id, enabled=enabled)


async def update_scan_status(
    db: aiosqlite.Connection,
    source_id: int,
    status: str,
) -> None:
    """Update last scan time and status for a source.

    Args:
        db: Database connection.
        source_id: Source ID.
        status: Status string ('ok', 'error', 'running').
    """
    now = datetime.now(UTC).isoformat()

    await db.execute(
        "UPDATE scan_sources SET last_scan_at = ?, last_scan_status = ? WHERE id = ?",
        (now, status, source_id),
    )
    await db.commit()
