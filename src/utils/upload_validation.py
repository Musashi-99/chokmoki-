"""Validate admin media uploads: size cap, extension whitelist, magic-byte sniffing."""

from __future__ import annotations

from typing import Optional, Tuple

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB

ALLOWED_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp", "avif", "mp4"})

CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "avif": "image/avif",
    "mp4": "video/mp4",
}


class UploadValidationError(ValueError):
    """Raised when uploaded bytes fail security checks."""


def _detect_type_from_magic(content: bytes) -> Optional[str]:
    if len(content) < 12:
        return None

    if content[:3] == b"\xff\xd8\xff":
        return "jpeg"

    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"

    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"

    if content[4:8] == b"ftyp":
        brand = content[8:12]
        if brand in (b"avif", b"avis"):
            return "avif"
        if brand.startswith(b"mp") or brand in (
            b"isom",
            b"iso2",
            b"M4V ",
            b"MSNV",
            b"ndas",
            b"ndsc",
            b"ndsh",
            b"ndsm",
            b"ndsp",
            b"ndss",
            b"ndxc",
            b"ndxh",
            b"ndxm",
            b"ndxp",
            b"ndxs",
        ):
            return "mp4"

    return None


def _normalize_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower().strip()


def validate_upload(content: bytes, filename: str) -> Tuple[str, str]:
    """
    Validate upload bytes and return (extension, content_type).
    Extension is normalized (jpeg not jpg when detected as JPEG).
    """
    if not content:
        raise UploadValidationError("Empty file")

    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadValidationError(
            f"File exceeds maximum size of {MAX_UPLOAD_BYTES // (1024 * 1024)}MB"
        )

    declared_ext = _normalize_extension(filename)
    if declared_ext == "jpg":
        declared_ext = "jpeg"
    if declared_ext and declared_ext not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(
            f"File type '.{declared_ext}' is not allowed. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    detected = _detect_type_from_magic(content)
    if not detected:
        raise UploadValidationError(
            "File content does not match an allowed image or video format"
        )

    if detected not in ALLOWED_EXTENSIONS:
        raise UploadValidationError("Detected file type is not allowed")

    if declared_ext and declared_ext != detected:
        raise UploadValidationError(
            f"File extension does not match content (expected .{detected})"
        )

    ext = detected
    if ext == "jpeg":
        storage_ext = "jpg"
    else:
        storage_ext = ext

    return storage_ext, CONTENT_TYPES[ext]
