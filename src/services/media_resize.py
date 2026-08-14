from io import BytesIO

from PIL import Image, ImageFile, UnidentifiedImageError

ImageFile.LOAD_TRUNCATED_IMAGES = True

_ALLOWED_WIDTHS = {160, 240, 360, 400, 480, 640, 768, 800, 828, 960, 1120, 1200, 1280, 1440, 1600, 1920}


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


def resize_image_bytes(body: bytes, content_type: str, width: int | None) -> tuple[bytes, str]:
    target = clamp_resize_width(width)
    if not target or not content_type.startswith("image/") or content_type == "image/svg+xml":
        return body, content_type
    try:
        with Image.open(BytesIO(body)) as image:
            image.load()
            if image.width <= target:
                return body, content_type
            ratio = target / float(image.width)
            height = max(1, round(image.height * ratio))
            resized = image.convert("RGB") if image.mode in ("P", "RGBA", "LA") else image
            resized = resized.resize((target, height), Image.Resampling.LANCZOS)
            out = BytesIO()
            fmt = "WEBP"
            resized.save(out, format=fmt, quality=82, method=4)
            return out.getvalue(), "image/webp"
    except (UnidentifiedImageError, OSError, ValueError):
        return body, content_type
