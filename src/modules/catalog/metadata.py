"""Metadata extraction for images and videos."""

import json
import logging
import subprocess
from io import BytesIO
from typing import Any, Optional

from PIL import Image
from PIL.Image import Image as PILImage

logger = logging.getLogger(__name__)


def extract_image_metadata(img_bytes: bytes) -> dict[str, Any]:
    """Extract metadata from image bytes.

    Uses Pillow to extract dimensions, format, and EXIF data.

    Args:
        img_bytes: Image file bytes.

    Returns:
        Metadata dict with width, height, format, exif data.
    """
    metadata: dict[str, Any] = {}
    try:
        img = Image.open(BytesIO(img_bytes))
        metadata["width"] = img.width
        metadata["height"] = img.height
        metadata["format"] = img.format or "unknown"

        # Extract EXIF if available
        exif: dict[str, Any] = {}
        try:
            exif_data = img.getexif()
            if exif_data:
                # Try to extract common EXIF tags
                if 306 in exif_data:  # DateTime
                    exif["datetime"] = str(exif_data[306])
                if 271 in exif_data:  # Make (camera brand)
                    exif["make"] = str(exif_data[271])
                if 272 in exif_data:  # Model (camera model)
                    exif["model"] = str(exif_data[272])
        except Exception as e:
            logger.debug(f"Failed to extract EXIF: {e}")

        metadata["exif"] = exif
        logger.info(f"Extracted image metadata: {metadata['width']}x{metadata['height']} {metadata['format']}")
    except Exception as e:
        logger.error(f"Failed to extract image metadata: {e}")
        metadata = {"format": "unknown"}

    return metadata


def extract_video_metadata(dropbox_path: str) -> dict[str, Any]:
    """Extract metadata from video using ffprobe.

    Args:
        dropbox_path: Path to video in Dropbox (will be fetched before probing).

    Returns:
        Metadata dict with duration, resolution, codec.

    Note:
        This function expects the video file to already be downloaded locally.
        Use with a temporary file path.
    """
    metadata: dict[str, Any] = {}
    try:
        # Call ffprobe
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_format", "-show_streams",
                "-of", "json",
                dropbox_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(f"ffprobe failed for {dropbox_path}: {result.stderr}")
            return metadata

        data = json.loads(result.stdout)

        # Extract duration from format
        if "format" in data and "duration" in data["format"]:
            metadata["duration_seconds"] = float(data["format"]["duration"])

        # Extract video stream info (first video stream)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                if "width" in stream:
                    metadata["width"] = stream["width"]
                if "height" in stream:
                    metadata["height"] = stream["height"]
                if "codec_name" in stream:
                    metadata["codec"] = stream["codec_name"]
                if "r_frame_rate" in stream:
                    try:
                        parts = stream["r_frame_rate"].split("/")
                        metadata["fps"] = float(parts[0]) / float(parts[1]) if len(parts) == 2 else float(parts[0])
                    except (ValueError, IndexError):
                        pass
                break

        logger.info(f"Extracted video metadata: {metadata}")
    except FileNotFoundError:
        logger.warning("ffprobe not found, skipping video metadata extraction")
    except Exception as e:
        logger.error(f"Failed to extract video metadata: {e}")

    return metadata


def get_media_type(mime_type: str) -> str:
    """Determine media type from MIME type.

    Args:
        mime_type: MIME type string.

    Returns:
        "image" or "video".
    """
    if mime_type.startswith("image/"):
        return "image"
    elif mime_type.startswith("video/"):
        return "video"
    return "unknown"


def is_supported_image(mime_type: str) -> bool:
    """Check if MIME type is a supported image format.

    Args:
        mime_type: MIME type string.

    Returns:
        True if supported.
    """
    supported = {
        "image/jpeg", "image/png", "image/webp", "image/gif",
        "image/svg+xml", "image/tiff",
    }
    return mime_type in supported


def is_supported_video(mime_type: str) -> bool:
    """Check if MIME type is a supported video format.

    Args:
        mime_type: MIME type string.

    Returns:
        True if supported.
    """
    supported = {
        "video/mp4", "video/webm", "video/mpeg", "video/quicktime",
        "video/x-msvideo", "video/x-matroska",
    }
    return mime_type in supported
