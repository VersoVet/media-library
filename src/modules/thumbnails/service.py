"""Thumbnail generation service."""

import logging
import os
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

THUMBNAIL_DIR = Path(os.getenv("MEDIA_LIBRARY_THUMB_PATH", "/opt/onyx/data/media-library/thumbnails"))
THUMBNAIL_SIZE = (320, 320)
THUMBNAIL_FORMAT = "webp"


async def ensure_thumbnail_dir() -> None:
    """Create thumbnail directory if it doesn't exist."""
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)


def get_thumbnail_path(media_id: str, is_video: bool = False) -> Path:
    """Get path to thumbnail file.

    Args:
        media_id: Media ID.
        is_video: If True, returns .gif path; otherwise .webp.

    Returns:
        Path to thumbnail file.
    """
    ext = "gif" if is_video else THUMBNAIL_FORMAT
    return THUMBNAIL_DIR / f"{media_id}.{ext}"


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


async def generate_video_thumbnail(dropbox_path: str, media_id: str) -> Path | None:
    """Generate lightweight GIF thumbnail for video.

    Extracts frames from 0.5-1.5 seconds and creates a short looping GIF.

    Args:
        dropbox_path: Path to video in Dropbox (must be downloaded first).
        media_id: Media ID (for filename).

    Returns:
        Path to generated GIF thumbnail, or None if generation fails.

    Note:
        This function expects the video file to be available locally.
        Use with a temporary file path.
    """
    await ensure_thumbnail_dir()
    # Change extension to .gif instead of .webp
    thumb_path = THUMBNAIL_DIR / f"{media_id}.gif"

    try:
        # Extract 5 frames over 1 second (0.5-1.5 seconds) for animation
        with tempfile.TemporaryDirectory() as tmpdir:
            # Extract frames
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    dropbox_path,
                    "-ss",
                    "0.5",
                    "-t",
                    "1",
                    "-vf",
                    "scale=320:-1,fps=5",
                    os.path.join(tmpdir, "frame_%d.png"),
                ],
                capture_output=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.warning(f"ffmpeg extract failed: {result.stderr.decode()}")
                return None

            # Load frames and create GIF
            frames = []
            for i in range(1, 6):  # 5 frames
                frame_path = os.path.join(tmpdir, f"frame_{i}.png")
                if os.path.exists(frame_path):
                    try:
                        img = Image.open(frame_path)
                        img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                        # Convert RGBA to RGB for GIF compatibility
                        if img.mode in ("RGBA", "LA", "P"):
                            bg = Image.new("RGB", img.size, (240, 240, 240))
                            if img.mode == "P":
                                img = img.convert("RGBA")
                            bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                            img = bg
                        frames.append(img)
                    except Exception as e:
                        logger.debug(f"Could not load frame {i}: {e}")

            if not frames:
                logger.warning(f"No frames extracted for {media_id}")
                return None

            # Save as animated GIF with heavy compression
            frames[0].save(
                str(thumb_path),
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=200,  # 200ms per frame
                loop=0,  # Infinite loop
                optimize=True,  # Compress
            )

            logger.info(f"Generated GIF thumbnail {media_id}: {thumb_path}")
            return thumb_path

    except FileNotFoundError:
        logger.warning("ffmpeg not found, skipping video thumbnail")
        return None
    except Exception as e:
        logger.error(f"Failed to generate video thumbnail: {e}")
        return None
