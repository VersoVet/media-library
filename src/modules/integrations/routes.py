"""Integration API routes (paper-reader webhook)."""

import logging
from typing import Any

import aiomysql
from fastapi import APIRouter, Depends, HTTPException

from src.database import fetchall, get_db
from src.models import PaperCollection, PaperReaderPayload

from . import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["integrations"])


@router.post("/import/paper-reader")
async def import_paper_figures(
    payload: PaperReaderPayload,
    conn: aiomysql.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Import figures from paper-reader.

    Called by paper-reader when figures are extracted from an article.
    Creates a collection for the article and imports all figures.

    Args:
        payload: Paper reader payload with zotero_key, article_title, figures.
        conn: Database connection.

    Returns:
        Import result with album_id, imported_count, errors.
    """
    try:
        result = await service.import_paper_figures(
            conn=conn,
            zotero_key=payload.zotero_key,
            article_title=payload.article_title,
            figures=[f.model_dump() for f in payload.figures],
            article_metadata=payload.article_metadata,
        )
        return result
    except Exception as e:
        logger.error(f"Paper import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/paper-collections")
async def list_paper_collections(
    conn: aiomysql.Connection = Depends(get_db),
) -> list[PaperCollection]:
    """List all paper collections.

    Args:
        conn: Database connection.

    Returns:
        List of paper collections with zotero keys and album IDs.
    """
    rows = await fetchall(conn, "SELECT * FROM ml_paper_collections ORDER BY created_at DESC")
    results = []
    for r in rows:
        import json

        results.append(
            PaperCollection(
                id=r["id"],
                zotero_key=r["zotero_key"],
                article_title=r["article_title"],
                album_id=r.get("album_id"),
                article_metadata=json.loads(r.get("article_metadata", "{}")) if r.get("article_metadata") else {},
                created_at=r.get("created_at"),
                updated_at=r.get("updated_at"),
            )
        )
    return results


@router.get("/paper-collections/{zotero_key}")
async def get_paper_collection(
    zotero_key: str,
    conn: aiomysql.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Get paper collection with its media.

    Args:
        zotero_key: Zotero item key.
        conn: Database connection.

    Returns:
        Paper collection with album info and media list.
    """
    from src.database import fetchone

    row = await fetchone(
        conn,
        "SELECT * FROM ml_paper_collections WHERE zotero_key = %s",
        (zotero_key,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Paper collection not found")

    import json

    collection = {
        "id": row["id"],
        "zotero_key": row["zotero_key"],
        "article_title": row["article_title"],
        "album_id": row.get("album_id"),
        "article_metadata": json.loads(row.get("article_metadata", "{}")) if row.get("article_metadata") else {},
    }

    # Fetch media in this album
    if collection["album_id"]:
        from src.modules.albums import service as albums_service

        media_list, total = await albums_service.get_album_media(conn, collection["album_id"], limit=100)
        collection["media_count"] = total
        collection["media"] = media_list

    return collection
