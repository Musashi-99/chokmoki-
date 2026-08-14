from io import BytesIO

from PIL import Image

from src.services.media_resize import clamp_resize_width, resize_image_bytes, cache_headers


def _png(width: int, height: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), (200, 160, 90)).save(buf, format="PNG")
    return buf.getvalue()


def test_clamp_resize_width_snaps_to_ladder():
    assert clamp_resize_width(None) is None
    assert clamp_resize_width(0) is None
    assert clamp_resize_width(400) == 400
    assert clamp_resize_width(401) == 480
    assert clamp_resize_width(9999) == 1920


def test_resize_image_bytes_shrinks_wide_png_to_webp():
    original = _png(2000, 2000)
    body, content_type = resize_image_bytes(original, "image/png", 400)
    assert content_type == "image/webp"
    assert len(body) < len(original)
    with Image.open(BytesIO(body)) as image:
        assert image.width == 400
        assert image.height == 400


def test_cache_headers_suffix_width_on_etag():
    headers = cache_headers('"abc"', 400)
    assert headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert headers["ETag"] == '"abc-w400"'


def test_cache_headers_passthrough_without_width():
    headers = cache_headers('"abc"', None)
    assert headers["ETag"] == '"abc"'
    assert headers["Cache-Control"] == "public, max-age=31536000, immutable"


def test_cache_headers_without_etag_still_tags_width():
    headers = cache_headers(None, 800)
    assert headers["ETag"] == '"w800"'


def test_resize_image_bytes_skips_when_already_small():
    original = _png(200, 200)
    body, content_type = resize_image_bytes(original, "image/png", 400)
    assert body == original
    assert content_type == "image/png"
