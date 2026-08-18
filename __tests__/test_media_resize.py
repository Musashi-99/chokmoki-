from io import BytesIO

from PIL import Image

from src.services.media_resize import (
    cache_headers,
    clamp_resize_width,
    read_disk_cache,
    recompress_upload,
    resize_image_bytes,
    serve_width,
    write_disk_cache,
)


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


def test_serve_width_caps_uncapped_images_at_1920():
    assert serve_width(None, "image/jpeg") == 1920
    assert serve_width(400, "image/jpeg") == 400
    assert serve_width(None, "video/mp4") is None
    assert serve_width(None, "image/svg+xml") is None


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


def test_resize_image_bytes_recompresses_small_png_to_webp():
    original = _png(200, 200)
    body, content_type = resize_image_bytes(original, "image/png", 400)
    assert content_type == "image/webp"
    with Image.open(BytesIO(body)) as image:
        assert image.width == 200


def test_recompress_upload_skips_video():
    blob = b"not-an-image"
    body, content_type = recompress_upload(blob, "video/mp4")
    assert body == blob
    assert content_type == "video/mp4"


def test_disk_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CHOKMOKI_MEDIA_CACHE", str(tmp_path))
    body = b"webp-bytes"
    write_disk_cache("chokmoki/hero/a.jpg", '"etag1"', 828, body, "image/webp")
    cached = read_disk_cache("chokmoki/hero/a.jpg", '"etag1"', 828)
    assert cached == (body, "image/webp")
    assert read_disk_cache("chokmoki/hero/a.jpg", '"etag2"', 828) is None
