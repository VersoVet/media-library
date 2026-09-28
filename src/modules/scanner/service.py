"""Scanner service for multi-source orchestration."""

import json
import logging
from typing import Any

import aiomysql

from src.models import SyncReport
from src.modules.scanner import dropbox_scanner, local_scanner, ssh_scanner
from src.modules.sources import service as sources_service

logger = logging.getLogger(__name__)


async def scan_source(
    conn: aiomysql.Connection,
    source: dict[str, Any],
) -> SyncReport:
    """Scan a source and import new media.

    Args:
        conn: Database connection.
        source: Source dict from database.

    Returns:
        Sync report with import statistics.
    """
    source_id = source["id"]
    source_type = source["source_type"]
    if "config" in source and isinstance(source["config"], dict):
        config = source["config"]
    else:
        config = json.loads(source.get("config_json", "{}"))

    await sources_service.update_scan_status(conn, source_id, "running")

    # Signal WORKING status for visibility
    try:
        from src.main import onyx

        if onyx:
            try:
                onyx.status("WORKING")
            except (AttributeError, TypeError):
                pass
    except ImportError:
        pass

    try:
        if source_type == "dropbox":
            report = await dropbox_scanner.scan_dropbox_source(conn, source_id, config, source)
        elif source_type == "local":
            report = await local_scanner.scan_local_source(conn, source_id, config, source)
        elif source_type == "ssh":
            report = await ssh_scanner.scan_ssh_source(conn, source_id, config, source)
        else:
            raise ValueError(f"Unknown source type: {source_type}")

        await sources_service.update_scan_status(conn, source_id, "ok")
        logger.info(f"Scan complete for source {source_id}: {report}")

        # Restore UP status
        try:
            from src.main import onyx

            if onyx:
                try:
                    onyx.status("UP")
                except (AttributeError, TypeError):
                    pass
        except ImportError:
            pass

        return report

    except Exception as e:
        logger.error(f"Scan failed for source {source_id}: {e}")
        await sources_service.update_scan_status(conn, source_id, "error")
        raise


async def scan_all_enabled_sources(conn: aiomysql.Connection) -> list[SyncReport]:
    """Scan all enabled sources.

    Args:
        conn: Database connection.

    Returns:
        List of sync reports.
    """
    sources = await sources_service.list_sources(conn)
    reports = []

    for source_row in sources:
        if not source_row.get("enabled", False):
            continue

        try:
            report = await scan_source(conn, source_row)
            reports.append(report)
        except Exception as e:
            logger.error(f"Scan failed for source {source_row['id']}: {e}")

    return reports
