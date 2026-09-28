"""File-serving and research-hub integration routes."""

import logging
import mimetypes
from typing import Any

import aiomysql
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.database import IMAGE_CATEGORY_IMAGE, fetchall, get_db
from src.models import (
    CopyToRequest,
    CopyToResponse,
    MediaBatchItem,
    MediaBatchResponse,
    MediaUrl,
)
from src.modules.storage.registry import get_backend

from . import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["files"])


@router.get("/media/{image_id}/url", response_model=MediaUrl)
async def get_media_url(
    image_id: int,
    conn: aiomysql.Connection = Depends(get_db),
) -> MediaUrl:
    """Get permanent URL for media file in full resolution.

    Args:
        image_id: Media ID.
        conn: Database connection.

    Returns:
        MediaUrl with permanent URL, filename, dimensions.
    """
    media = await service.get_media(conn, image_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    backend_name = media.get("storage_backend", "nas")
    storage_path = media.get("storage_path", "")

    try:
        backend = get_backend(backend_name)
        url = await backend.get_url(storage_path)
    except Exception as e:
        logger.error(f"Failed to get URL for media {image_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate URL")

    return MediaUrl(
        url=url,
        media_id=image_id,
        filename=media.get("name", ""),
        width=media.get("width"),
        height=media.get("height"),
    )


@router.get("/media/batch", response_model=MediaBatchResponse)
async def get_media_batch(
    ids: str = Query(..., description="Comma-separated media IDs (max 50)"),
    conn: aiomysql.Connection = Depends(get_db),
) -> MediaBatchResponse:
    """Get details for multiple media items in one call.

    Args:
        ids: Comma-separated media IDs.
        conn: Database connection.

    Returns:
        Batch response with media details including URLs.
    """
    id_list = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
    if not id_list:
        return MediaBatchResponse(media=[])
    if len(id_list) > 50:
        raise HTTPException(status_code=400, detail="Max 50 IDs per batch")

    placeholders = ",".join(["%s"] * len(id_list))
    rows = await fetchall(
        conn,
        f"""SELECT i.id, i.name, i.category, i.fileSize,
                   ii.width, ii.height, ii.creationDate
            FROM Images i
            LEFT JOIN ImageInformation ii ON i.id = ii.imageid
            WHERE i.id IN ({placeholders}) AND i.status = 1""",
        tuple(id_list),
    )

    items = []
    for row in rows:
        img_id = row["id"]
        props = await fetchall(
            conn,
            "SELECT property, value FROM ImageProperties WHERE imageid = %s AND property LIKE 'ml:%%'",
            (img_id,),
        )
        prop_dict = {p["property"].replace("ml:", ""): p["value"] for p in props}

        tags = await fetchall(
            conn,
            "SELECT t.name FROM Tags t JOIN ImageTags it ON t.id = it.tagid WHERE it.imageid = %s AND t.pid >= 0",
            (img_id,),
        )

        url = await _get_media_url(prop_dict)
        media_type = "image" if row.get("category") == IMAGE_CATEGORY_IMAGE else "video"

        items.append(
            MediaBatchItem(
                id=img_id,
                title=prop_dict.get("title", row["name"]),
                media_type=media_type,
                url=url,
                thumbnail_url=f"/api/media/{img_id}/thumbnail",
                tags=[t["name"] for t in tags],
                width=row.get("width"),
                height=row.get("height"),
            )
        )

    return MediaBatchResponse(media=items)


@router.post("/media/{image_id}/copy-to", response_model=CopyToResponse)
async def copy_media_to(
    image_id: int,
    request: CopyToRequest,
    conn: aiomysql.Connection = Depends(get_db),
) -> CopyToResponse:
    """Copy media file to another folder.

    Args:
        image_id: Media ID.
        request: Destination folder.
        conn: Database connection.

    Returns:
        URL and path of the copy.
    """
    media = await service.get_media(conn, image_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    backend_name = media.get("storage_backend", "nas")
    storage_path = media.get("storage_path", "")

    try:
        backend = get_backend(backend_name)
        file_bytes = await backend.download(storage_path)
        dest_path = f"{request.destination_folder.rstrip('/')}/{media['name']}"
        await backend.upload(file_bytes, dest_path)
        url = await backend.get_url(dest_path)
        return CopyToResponse(url=url, path=dest_path)
    except Exception as e:
        logger.error(f"Copy failed for media {image_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/{path:path}")
async def serve_file(path: str) -> StreamingResponse:
    """Stream a file from NAS storage.

    Args:
        path: Relative file path within NAS storage.

    Returns:
        File stream with appropriate content type.
    """
    try:
        from src.modules.storage.nas import NASStorage

        nas = get_backend("nas")
        if not isinstance(nas, NASStorage):
            raise HTTPException(status_code=501, detail="NAS backend not available")

        full_path = nas.get_full_path(path)
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        content_type = mimetypes.guess_type(str(full_path))[0] or "application/octet-stream"

        async def file_iterator():
            import aiofiles

            async with aiofiles.open(full_path, "rb") as f:
                while chunk := await f.read(65536):
                    yield chunk

        return StreamingResponse(file_iterator(), media_type=content_type)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"File serving failed for {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _get_media_url(prop_dict: dict[str, Any]) -> str:
    """Get URL for a media item from its properties.

    Args:
        prop_dict: Media properties dict.

    Returns:
        URL string.
    """
    backend_name = prop_dict.get("storage_backend", "nas")
    storage_path = prop_dict.get("storage_path", "")
    try:
        backend = get_backend(backend_name)
        return await backend.get_url(storage_path)
    except Exception:
        return ""
