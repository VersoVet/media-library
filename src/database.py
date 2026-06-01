"""Database initialization and management."""

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import aiosqlite

DB_PATH = Path(os.getenv("MEDIA_LIBRARY_DB_PATH", "/opt/onyx/data/media-library/media.db"))


async def init_db() -> None:
    """Initialize SQLite database with schema."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        # Media table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS media (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                media_type TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                dropbox_path TEXT NOT NULL,
                source_id INTEGER,
                source_path TEXT,
                file_size INTEGER NOT NULL,
                file_hash TEXT,
                width INTEGER,
                height INTEGER,
                duration_seconds REAL,
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (source_id) REFERENCES scan_sources(id)
            )
            """
        )

        # Migration: add file_hash column if it doesn't exist
        try:
            await db.execute("SELECT file_hash FROM media LIMIT 1")
        except Exception:
            # Column doesn't exist, add it
            await db.execute("ALTER TABLE media ADD COLUMN file_hash TEXT")

        # Tags table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
            """
        )

        # Media-Tags junction (N:N relation)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS media_tags (
                media_id TEXT REFERENCES media(id) ON DELETE CASCADE,
                tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (media_id, tag_id)
            )
            """
        )

        # FTS5 virtual table for full-text search
        await db.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS media_fts USING fts5(
                title,
                description,
                tags,
                content='media',
                content_rowid='rowid'
            )
            """
        )

        # Scan sources table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                config_json TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                recursive INTEGER DEFAULT 1,
                auto_tag INTEGER DEFAULT 1,
                cron_schedule TEXT DEFAULT '0 */6 * * *',
                last_scan_at TEXT,
                last_scan_status TEXT
            )
            """
        )

        # Scan logs table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER REFERENCES scan_sources(id),
                started_at TEXT NOT NULL,
                finished_at TEXT,
                files_found INTEGER DEFAULT 0,
                files_imported INTEGER DEFAULT 0,
                files_skipped INTEGER DEFAULT 0,
                errors_json TEXT DEFAULT '[]'
            )
            """
        )

        await db.commit()


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Get async database connection.

    Yields:
        SQLite connection.
    """
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def get_db_context() -> aiosqlite.Connection:
    """Get database connection for context managers (not FastAPI dependency).

    Returns:
        SQLite connection.
    """
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys=ON")
    return db
