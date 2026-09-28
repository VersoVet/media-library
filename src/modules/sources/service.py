"""Source management service for scan configuration (MariaDB)."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

import aiomysql

from src.database import execute, fetchall, fetchone, insert

logger = logging.getLogger(__name__)


async def create_source(
    conn: aiomysql.Connection,
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
        conn: Database connection.
        name: Source name.
        source_type: Type ('dropbox', 'local', 'ssh', 'nas').
        config: Source configuration dict.
        enabled: Whether source is enabled.
        recursive: Scan subfolders.
        auto_tag: Suggest tags for new imports.
        cron_schedule: Cron expression.

    Returns:
        Source ID.

    Raises:
        ValueError: If source_type invalid.
    """
    valid_types = ("dropbox", "local", "ssh", "nas")
    if source_type not in valid_types:
        raise ValueError(f"Invalid source_type: {source_type}. Must be one of {valid_types}")

    source_id = await insert(
        conn,
        """INSERT INTO ml_scan_sources
           (name, source_type, config_json, enabled, `recursive`, `auto_tag`, cron_schedule)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (name, source_type, json.dumps(config), int(enabled), int(recursive), int(auto_tag), cron_schedule),
    )

    logger.info(f"Created scan source {source_id}: {name}")
    return source_id


async def get_source(conn: aiomysql.Connection, source_id: int) -> dict[str, Any] | None:
    """Get source by ID.

    Args:
        conn: Database connection.
        source_id: Source ID.

    Returns:
        Source dict with parsed config, or None.
    """
    row = await fetchone(conn, "SELECT * FROM ml_scan_sources WHERE id = %s", (source_id,))
    if not row:
        return None
    return _parse_source(row)


async def list_sources(conn: aiomysql.Connection) -> list[dict[str, Any]]:
    """List all scan sources.

    Args:
        conn: Database connection.

    Returns:
        List of source dicts.
    """
    rows = await fetchall(conn, "SELECT * FROM ml_scan_sources ORDER BY name")
    return [_parse_source(r) for r in rows]


async def update_source(conn: aiomysql.Connection, source_id: int, **kwargs: Any) -> bool:
    """Update source fields.

    Args:
        conn: Database connection.
        source_id: Source ID.
        **kwargs: Fields to update.

    Returns:
        True if updated.
    """
    updates = []
    values: list[Any] = []

    field_map = {
        "name": "name",
        "config": "config_json",
        "enabled": "enabled",
        "recursive": "`recursive`",
        "auto_tag": "`auto_tag`",
        "cron_schedule": "cron_schedule",
    }

    for key, col in field_map.items():
        if key in kwargs:
            updates.append(f"{col} = %s")
            val = kwargs[key]
            if key == "config":
                val = json.dumps(val)
            elif key in ("enabled", "recursive", "auto_tag"):
                val = int(val)
            values.append(val)

    if not updates:
        return False

    values.append(source_id)
    affected = await execute(conn, f"UPDATE ml_scan_sources SET {', '.join(updates)} WHERE id = %s", tuple(values))
    if affected > 0:
        logger.info(f"Updated scan source {source_id}")
    return affected > 0


async def delete_source(conn: aiomysql.Connection, source_id: int) -> bool:
    """Delete source by ID.

    Args:
        conn: Database connection.
        source_id: Source ID.

    Returns:
        True if deleted.
    """
    affected = await execute(conn, "DELETE FROM ml_scan_sources WHERE id = %s", (source_id,))
    if affected > 0:
        logger.info(f"Deleted scan source {source_id}")
    return affected > 0


async def toggle_source(conn: aiomysql.Connection, source_id: int, enabled: bool) -> bool:
    """Enable or disable a source.

    Args:
        conn: Database connection.
        source_id: Source ID.
        enabled: New enabled state.

    Returns:
        True if updated.
    """
    return await update_source(conn, source_id, enabled=enabled)


async def update_scan_status(conn: aiomysql.Connection, source_id: int, status: str) -> None:
    """Update last scan time and status.

    Args:
        conn: Database connection.
        source_id: Source ID.
        status: Status string ('ok', 'error', 'running').
    """
    now = datetime.now(UTC)
    await execute(
        conn,
        "UPDATE ml_scan_sources SET last_scan_at = %s, last_scan_status = %s WHERE id = %s",
        (now, status, source_id),
    )


def _parse_source(row: dict[str, Any]) -> dict[str, Any]:
    """Parse source row from database.

    Args:
        row: Raw database row.

    Returns:
        Parsed source dict.
    """
    source = dict(row)
    source["config"] = json.loads(source.get("config_json", "{}"))
    if "config_json" in source:
        del source["config_json"]
    source["enabled"] = bool(source.get("enabled", 0))
    source["recursive"] = bool(source.get("recursive", 0))
    source["auto_tag"] = bool(source.get("auto_tag", 0))
    return source
