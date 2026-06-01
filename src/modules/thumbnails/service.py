"""Thumbnail generation service."""

import logging
import os
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

THUMBNAIL_DIR = Path(os.getenv("MEDIA_LIBRARY_THUMB_PATH", "/opt/onyx/data/media-library/thumbnails"))
THUMBNAIL_SIZE = (320, 320)
THUMBNAIL_FORMAT = "webp"


async def ensure_thumbnail_dir() -> None:
    """Create thumbnail directory if it doesn't exist."""
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)


def get_thumbnail_path(media_id: str) -> Path:
    """Get path to thumbnail file.

    Args:
        media_id: Media ID.

    Returns:
        Path to thumbnail webp file.
    """
    return THUMBNAIL_DIR / f"{media_id}.{THUMBNAIL_FORMAT}"


async def generate_image_thumbnail(img_bytes: bytes, media_id: str) -> Path:
    """Generate thumbnail for image.

    Args:
        img_bytes: Image file bytes.
        media_id: Media ID (for filename).

    Returns:
        Path to generated thumbnail.

    Raises:
        Exception: If generation fails.
    """
    await ensure_thumbnail_dir()
    thumb_path = get_thumbnail_path(media_id)

    try:
        # Open image
        img = Image.open(BytesIO(img_bytes))

        # Resize maintaining aspect ratio
        img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

        # Save as webp
        img.save(str(thumb_path), format="WEBP", quality=80)
        logger.info(f"Generated image thumbnail {media_id}: {thumb_path}")
        return thumb_path

    except Exception as e:
        logger.error(f"Failed to generate image thumbnail: {e}")
        raise


async def generate_video_thumbnail(dropbox_path: str, media_id: str) -> Optional[Path]:
    """Generate thumbnail for video.

    Extracts a frame at 1 second using ffmpeg, then resizes.

    Args:
        dropbox_path: Path to video in Dropbox (must be downloaded first).
        media_id: Media ID (for filename).

    Returns:
        Path to generated thumbnail, or None if generation fails.

    Note:
        This function expects the video file to be available locally.
        Use with a temporary file path.
    """
    await ensure_thumbnail_dir()
    thumb_path = get_thumbnail_path(media_id)

    try:
        # Extract frame at 1 second
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_frame = tmp.name

        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-i", dropbox_path,
                    "-ss", "1",
                    "-vf", "scale=320:-1",
                    "-vframes", "1",
                    tmp_frame,
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(f"ffmpeg failed: {result.stderr.decode()}")
                return None

            # Convert PNG to WebP
            img = Image.open(tmp_frame)
            img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            img.save(str(thumb_path), format="WEBP", quality=80)

            logger.info(f"Generated video thumbnail {media_id}: {thumb_path}")
            return thumb_path

        finally:
            # Clean up temp frame
            if os.path.exists(tmp_frame):
                os.unlink(tmp_frame)

    except FileNotFoundError:
        logger.warning("ffmpeg not found, skipping video thumbnail")
        return None
    except Exception as e:
        logger.error(f"Failed to generate video thumbnail: {e}")
        return None
