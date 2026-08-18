from io import BytesIO
import hashlib
import os
from pathlib import Path

from PIL import Image, ImageFile, UnidentifiedImageError

ImageFile.LOAD_TRUNCATED_IMAGES = True

_ALLOWED_WIDTHS = {160, 240, 360, 400, 480, 640, 768, 800, 828, 960, 1120, 1200, 1280, 1440, 1600, 1920}
DEFAULT_CAP_WIDTH = 1920


def cache_headers(etag: str | None, width: int | None) -> dict[str, str]:
    headers = {"Cache-Control": "public, max-age=31536000, immutable"}
    if etag:
        tag = str(etag).strip('"')
        headers["ETag"] = f'"{tag}-w{width}"' if width else f'"{tag}"'
    elif width:
        headers["ETag"] = f'"w{width}"'
    return headers


def clamp_resize_width(width: int | None) -> int | None:
    if width is None:
        return None
    if width <= 0:
        return None
    allowed = sorted(_ALLOWED_WIDTHS)
    for candidate in allowed:
        if width <= candidate:
            return candidate
    return allowed[-1]


def serve_width(width: int | None, content_type: str) -> int | None:
    if not content_type.startswith("image/") or content_type == "image/svg+xml":
        return None
    return clamp_resize_width(width) or DEFAULT_CAP_WIDTH


def _cache_dir() -> Path:
    path = Path(os.environ.get("CHOKMOKI_MEDIA_CACHE", "/tmp/chokmoki-media"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def disk_cache_name(object_key: str, etag: str | None, width: int | None) -> str:
    tag = (etag or "none").strip('"')
    return hashlib.sha256(f"{object_key}|{tag}|{width or 0}".encode()).hexdigest()


def read_disk_cache(object_key: str, etag: str | None, width: int | None) -> tuple[bytes, str] | None:
    name = disk_cache_name(object_key, etag, width)
    body_path = _cache_dir() / name
    type_path = body_path.with_suffix(".type")
    if not body_path.exists() or not type_path.exists():
        return None
    try:
        return body_path.read_bytes(), type_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def write_disk_cache(
    object_key: str,
    etag: str | None,
    width: int | None,
    body: bytes,
    content_type: str,
) -> None:
    name = disk_cache_name(object_key, etag, width)
    body_path = _cache_dir() / name
    type_path = body_path.with_suffix(".type")
    try:
        body_path.write_bytes(body)
        type_path.write_text(content_type, encoding="utf-8")
    except OSError:
        return


def resize_image_bytes(body: bytes, content_type: str, width: int | None) -> tuple[bytes, str]:
    target = clamp_resize_width(width)
    if not target or not content_type.startswith("image/") or content_type == "image/svg+xml":
        return body, content_type
    try:
        with Image.open(BytesIO(body)) as image:
            image.load()
            if content_type == "image/webp" and image.width <= target:
                return body, content_type
            resized = image.convert("RGB") if image.mode in ("P", "RGBA", "LA") else image
            if image.width > target:
                ratio = target / float(image.width)
                height = max(1, round(image.height * ratio))
                resized = resized.resize((target, height), Image.Resampling.LANCZOS)
            out = BytesIO()
            resized.save(out, format="WEBP", quality=82, method=2)
            return out.getvalue(), "image/webp"
    except (UnidentifiedImageError, OSError, ValueError):
        return body, content_type


def recompress_upload(body: bytes, content_type: str, max_width: int = DEFAULT_CAP_WIDTH) -> tuple[bytes, str]:
    if not content_type.startswith("image/") or content_type == "image/svg+xml":
        return body, content_type
    return resize_image_bytes(body, content_type, max_width)
