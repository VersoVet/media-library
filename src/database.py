"""MariaDB database connection and helpers for Digikam-compatible schema."""

import logging
from collections.abc import AsyncGenerator
from typing import Any

import aiomysql

from src.config import get_db_config, get_vault_url

logger = logging.getLogger(__name__)

_pool: aiomysql.Pool | None = None


async def _get_db_password() -> str:
    """Retrieve database password from Vault.

    Returns:
        Database password string.
    """
    import os

    import httpx

    cfg = get_db_config()
    vault_key = cfg.get("password_vault_key", "digikam_db_password")
    vault_url = get_vault_url()
    token = os.getenv("ONYX_VAULT_TOKEN", "")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{vault_url}/vault/{vault_key}",
            headers={"X-Vault-Token": token},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json().get("value", "")


async def init_db() -> None:
    """Initialize MariaDB connection pool.

    Creates a pool of connections to the Digikam database.
    The schema is expected to already exist (created during deployment).
    """
    global _pool
    if _pool is not None:
        return

    cfg = get_db_config()
    password = await _get_db_password()

    _pool = await aiomysql.create_pool(
        host=cfg.get("host", "10.0.0.44"),
        port=cfg.get("port", 3306),
        db=cfg.get("name", "digikam"),
        user=cfg.get("user", "digikam"),
        password=password,
        minsize=1,
        maxsize=cfg.get("pool_size", 5),
        autocommit=True,
        charset="utf8mb4",
    )
    logger.info(f"MariaDB pool initialized: {cfg.get('host')}:{cfg.get('port')}/{cfg.get('name')}")


async def close_db() -> None:
    """Close the database connection pool."""
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        logger.info("MariaDB pool closed")


async def get_db() -> AsyncGenerator[aiomysql.Connection, None]:
    """Get async database connection from pool (FastAPI dependency).

    Yields:
        MariaDB connection with dict cursor.
    """
    if _pool is None:
        await init_db()
    async with _pool.acquire() as conn:  # type: ignore[union-attr]
        yield conn


async def get_db_context() -> aiomysql.Connection:
    """Get database connection for non-FastAPI context managers.

    Returns:
        MariaDB connection.
    """
    if _pool is None:
        await init_db()
    conn = await _pool.acquire()  # type: ignore[union-attr]
    return conn


async def release_db_context(conn: aiomysql.Connection) -> None:
    """Release a connection back to the pool.

    Args:
        conn: Connection to release.
    """
    if _pool is not None:
        _pool.release(conn)


async def fetchone(conn: aiomysql.Connection, query: str, args: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    """Execute query and fetch one row as dict.

    Args:
        conn: Database connection.
        query: SQL query.
        args: Query parameters.

    Returns:
        Row as dict or None.
    """
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(query, args)
        return await cur.fetchone()


async def fetchall(conn: aiomysql.Connection, query: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Execute query and fetch all rows as dicts.

    Args:
        conn: Database connection.
        query: SQL query.
        args: Query parameters.

    Returns:
        List of rows as dicts.
    """
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(query, args)
        return list(await cur.fetchall())


async def execute(conn: aiomysql.Connection, query: str, args: tuple[Any, ...] = ()) -> int:
    """Execute a write query and return affected rows.

    Args:
        conn: Database connection.
        query: SQL query.
        args: Query parameters.

    Returns:
        Number of affected rows.
    """
    async with conn.cursor() as cur:
        await cur.execute(query, args)
        return cur.rowcount


async def insert(conn: aiomysql.Connection, query: str, args: tuple[Any, ...] = ()) -> int:
    """Execute an INSERT and return the last inserted ID.

    Args:
        conn: Database connection.
        query: SQL INSERT query.
        args: Query parameters.

    Returns:
        Last inserted row ID.
    """
    async with conn.cursor() as cur:
        await cur.execute(query, args)
        return cur.lastrowid


async def check_health() -> dict[str, Any]:
    """Check database health.

    Returns:
        Health status dict with 'status' and 'tables' keys.
    """
    try:
        if _pool is None:
            return {"status": "not_initialized"}
        async with _pool.acquire() as conn:
            row = await fetchone(conn, "SELECT COUNT(*) AS cnt FROM Images")
            tables = await fetchall(conn, "SHOW TABLES")
            return {
                "status": "ok",
                "images": row["cnt"] if row else 0,
                "tables": len(tables),
            }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# -- Digikam-specific constants --

# Image status values (Digikam convention)
IMAGE_STATUS_VISIBLE = 1
IMAGE_STATUS_REMOVED = 2
IMAGE_STATUS_TRASHED = 3

# Image category values
IMAGE_CATEGORY_IMAGE = 1
IMAGE_CATEGORY_VIDEO = 3
IMAGE_CATEGORY_AUDIO = 2
IMAGE_CATEGORY_OTHER = 4

# AlbumRoot type values
ALBUMROOT_TYPE_VOLUME = 1
ALBUMROOT_TYPE_SPECIFIC = 2
ALBUMROOT_TYPE_NETWORK = 3
