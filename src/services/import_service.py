"""Parse and restore a site-content backup ZIP produced by
aurum-editorial/src/lib/contentBundle.ts (exportAllContentBundle).
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List


MAX_BUNDLE_BYTES = 500 * 1024 * 1024  # 500MB — export bundles can carry hundreds of product photos

ASSET_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "avif": "image/avif",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mov": "video/quicktime",
    "m4v": "video/x-m4v",
}


class BundleParseError(ValueError):
    """Raised when the uploaded file is not a well-formed content bundle ZIP."""


@dataclass
class ParsedBundle:
    sections: Dict[str, Any] = field(default_factory=dict)
    assets: Dict[str, bytes] = field(default_factory=dict)
    asset_urls: Dict[str, str] = field(default_factory=dict)  # zip path -> original source URL


def parse_bundle_zip(raw: bytes) -> ParsedBundle:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise BundleParseError("Uploaded file is not a valid ZIP archive") from e

    names = set(zf.namelist())
    if "content.json" not in names:
        raise BundleParseError("Bundle is missing content.json")

    try:
        content = json.loads(zf.read("content.json").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise BundleParseError("content.json is not valid JSON") from e

    sections = content.get("sections")
    if not isinstance(sections, dict):
        raise BundleParseError("content.json has no 'sections' object")

    asset_urls: Dict[str, str] = {}
    if "assets-manifest.csv" in names:
        manifest_text = zf.read("assets-manifest.csv").decode("utf-8-sig")
        for row in csv.DictReader(io.StringIO(manifest_text)):
            if row.get("Status") == "downloaded":
                file_path = row.get("File", "")
                url = row.get("Source URL", "")
                if file_path and url:
                    asset_urls[file_path] = url

    assets: Dict[str, bytes] = {}
    for path in asset_urls:
        if path in names:
            assets[path] = zf.read(path)

    return ParsedBundle(sections=sections, assets=assets, asset_urls=asset_urls)
