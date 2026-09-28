"""Integration service for paper-reader and external skills."""

import logging
from typing import Any

import aiomysql
import httpx

from src.database import fetchone, insert
from src.modules.albums import service as albums_service
from src.modules.catalog import service as catalog_service
from src.modules.storage.registry import get_default, get_default_name

logger = logging.getLogger(__name__)


async def import_paper_figures(
    conn: aiomysql.Connection,
    zotero_key: str,
    article_title: str,
    figures: list[dict[str, Any]],
    article_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Import figures from paper-reader into a collection.

    Creates an album for the article (if not exists), downloads each figure,
    uploads to storage, and creates catalog entries.

    Args:
        conn: Database connection.
        zotero_key: Zotero item key.
        article_title: Article title.
        figures: List of figure dicts with figure_id, label, caption, native_url.
        article_metadata: Optional article metadata (doi, authors, year).

    Returns:
        Import result with album_id, imported_count, errors.
    """
    # Check/create paper collection entry
    existing = await fetchone(
        conn,
        "SELECT id, album_id FROM ml_paper_collections WHERE zotero_key = %s",
        (zotero_key,),
    )

    if existing:
        album_id = existing["album_id"]
    else:
        # Create album for this article
        album_path = f"/papers/{zotero_key}"
        album_id = await albums_service.create_album(conn, relative_path=album_path, caption=article_title)

        # Create paper collection entry
        import json

        meta_json = json.dumps(article_metadata or {})
        await insert(
            conn,
            """INSERT INTO ml_paper_collections (zotero_key, article_title, album_id, article_metadata)
               VALUES (%s, %s, %s, %s)""",
            (zotero_key, article_title, album_id, meta_json),
        )

    imported = 0
    errors: list[str] = []

    for fig in figures:
        try:
            fig_id = fig.get("figure_id", "unknown")
            label = fig.get("label", "")
            caption = fig.get("caption", "")
            native_url = fig.get("native_url", "")

            if not native_url:
                errors.append(f"{fig_id}: no native_url")
                continue

            # Download figure from URL
            async with httpx.AsyncClient() as client:
                resp = await client.get(native_url, timeout=60.0, follow_redirects=True)
                resp.raise_for_status()
                file_bytes = resp.content

            # Determine extension from URL or content type
            content_type = resp.headers.get("content-type", "image/png")
            ext = _ext_from_content_type(content_type)
            filename = f"{fig_id}{ext}"

            # Upload to storage
            storage_path = f"papers/{zotero_key}/{filename}"
            backend = get_default()
            await backend.upload(file_bytes, storage_path)

            # Determine mime type
            mime_type = content_type.split(";")[0].strip()

            # Create catalog entry
            file_hash = catalog_service.calculate_file_hash(file_bytes)
            image_id = await catalog_service.create_media(
                conn=conn,
                name=filename,
                title=f"{label}: {caption[:80]}" if caption else label,
                description=caption,
                media_type="image",
                mime_type=mime_type,
                album_id=album_id,
                storage_backend=get_default_name(),
                storage_path=storage_path,
                file_size=len(file_bytes),
                metadata=_extract_basic_metadata(file_bytes),
                tags=["paper-figure", f"zotero:{zotero_key}", label] if label else ["paper-figure"],
                file_hash=file_hash,
            )

            imported += 1
            logger.info(f"Imported paper figure {fig_id} as media {image_id}")

        except Exception as e:
            error_msg = f"{fig.get('figure_id', '?')}: {e}"
            errors.append(error_msg)
            logger.warning(f"Failed to import figure: {error_msg}")

    logger.info(f"Paper import for {zotero_key}: {imported}/{len(figures)} imported")
    return {
        "zotero_key": zotero_key,
        "album_id": album_id,
        "imported_count": imported,
        "total_figures": len(figures),
        "errors": errors,
    }


def _ext_from_content_type(content_type: str) -> str:
    """Get file extension from content type.

    Args:
        content_type: MIME content type.

    Returns:
        File extension with dot.
    """
    type_map = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/tiff": ".tiff",
        "image/svg+xml": ".svg",
    }
    base_type = content_type.split(";")[0].strip()
    return type_map.get(base_type, ".png")


def _extract_basic_metadata(file_bytes: bytes) -> dict[str, Any]:
    """Extract basic image metadata.

    Args:
        file_bytes: Image file bytes.

    Returns:
        Metadata dict with width, height, format.
    """
    try:
        from src.modules.catalog.metadata import extract_image_metadata

        return extract_image_metadata(file_bytes)
    except Exception:
        return {}
