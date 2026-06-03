"""LLM-based tag suggestion service using Groq vision."""

import base64
import io
import json
import logging
import os
from typing import Any

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Max image dimension for vision API (pixels) - keeps base64 under ~1 MB
VISION_MAX_DIMENSION = 1024


async def get_groq_api_key() -> str:
    """Get Groq API key from Vault.

    Returns:
        Groq API key.

    Raises:
        ValueError: If key not available.
    """
    token = os.getenv("ONYX_VAULT_TOKEN", "")
    if not token:
        raise ValueError("ONYX_VAULT_TOKEN not set")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://10.0.0.44:8050/vault/groq_api_key",
            headers={"X-Vault-Token": token},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json().get("value", "")


async def suggest_tags(img_bytes: bytes, metadata: dict[str, Any]) -> list[str]:
    """Suggest tags for an image using Groq vision.

    Args:
        img_bytes: Image file bytes.
        metadata: Image metadata (dimensions, format, etc.).

    Returns:
        List of suggested tag strings.
    """
    try:
        # Get API key
        api_key = await get_groq_api_key()

        # Resize image to limit memory usage before base64 encoding
        img_b64 = _resize_and_encode(img_bytes)

        # Call Groq API with vision
        async with httpx.AsyncClient() as client:
            response = await client.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{img_b64}",
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": (
                                        "Analyze this image and suggest 8-12 descriptive tags in French. "
                                        'Return ONLY a JSON array of strings, e.g., ["tag1", "tag2"]. '
                                        "Focus on content, context, and technical aspects."
                                    ),
                                },
                            ],
                        }
                    ],
                    "max_tokens": 300,
                    "temperature": 0.2,
                },
                timeout=60.0,
            )

            # Free base64 string immediately after sending request
            del img_b64

            if response.status_code != 200:
                logger.warning(f"Groq API error ({response.status_code}): {response.text}")
                return await _fallback_tags(metadata)

            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Parse JSON from response
            try:
                # Extract JSON from the response (might be wrapped in markdown code blocks)
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                else:
                    json_str = content.strip()

                tags = json.loads(json_str)
                if isinstance(tags, list) and all(isinstance(t, str) for t in tags):
                    logger.info(f"Suggested {len(tags)} tags via Groq vision")
                    return tags
            except (json.JSONDecodeError, IndexError, KeyError) as e:
                logger.warning(f"Failed to parse Groq response: {e}")
                return await _fallback_tags(metadata)

    except Exception as e:
        logger.error(f"Groq vision request failed: {e}")
        return await _fallback_tags(metadata)

    return await _fallback_tags(metadata)


def _resize_and_encode(img_bytes: bytes) -> str:
    """Resize image to bounded dimensions and return base64-encoded JPEG.

    Prevents memory explosion when encoding large images for the vision API.
    A 100 MB raw image becomes ~200 KB JPEG after resize.

    Args:
        img_bytes: Original image bytes.

    Returns:
        Base64-encoded JPEG string.
    """
    img: Image.Image = Image.open(io.BytesIO(img_bytes))
    try:
        # Resize if either dimension exceeds limit
        if img.width > VISION_MAX_DIMENSION or img.height > VISION_MAX_DIMENSION:
            img.thumbnail((VISION_MAX_DIMENSION, VISION_MAX_DIMENSION), Image.Resampling.LANCZOS)

        # Convert to RGB (drop alpha) and encode as JPEG
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        encoded = base64.b64encode(buf.getvalue()).decode()
        buf.close()
        return encoded
    finally:
        img.close()


async def _fallback_tags(metadata: dict[str, Any]) -> list[str]:
    """Generate fallback tags from metadata when vision fails.

    Args:
        metadata: Image metadata (dimensions, format, EXIF, etc.).

    Returns:
        List of fallback tags based on metadata.
    """
    tags: list[str] = []

    # Add format tag
    fmt = metadata.get("format", "").lower()
    if fmt:
        tags.append(fmt)

    # Add size classification
    width = metadata.get("width", 0)
    height = metadata.get("height", 0)
    if width and height:
        if width >= 2000 or height >= 2000:
            tags.append("haute-resolution")
        elif width <= 480 or height <= 480:
            tags.append("basse-resolution")
        if width > height:
            tags.append("paysage")
        elif height > width:
            tags.append("portrait")

    # Add EXIF tags if available
    exif = metadata.get("exif", {})
    if "make" in exif:
        tags.append(exif["make"].lower())
    if "model" in exif:
        tags.append(exif["model"].lower())
    if "datetime" in exif:
        tags.append("date-metadata")

    logger.info(f"Generated {len(tags)} fallback tags from metadata")
    return tags if tags else ["non-categorise"]
