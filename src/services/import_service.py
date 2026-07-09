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


from bson import ObjectId
from bson.errors import InvalidId

from src.services.cache_service import cache


@dataclass
class ImportResult:
    sections_restored: List[str] = field(default_factory=list)
    sections_skipped: List[str] = field(default_factory=list)
    sections_skip_reasons: Dict[str, str] = field(default_factory=dict)
    assets_restored: int = 0
    assets_failed: int = 0


def _asset_extension(zip_path: str) -> str:
    if "." not in zip_path:
        return "bin"
    return zip_path.rsplit(".", 1)[-1].lower()


async def _upload_assets(parsed: ParsedBundle, r2_service) -> tuple[Dict[str, str], int, int]:
    """Upload every bundled asset to R2. Returns (old_url -> new_url map, restored, failed)."""
    url_map: Dict[str, str] = {}
    restored = 0
    failed = 0
    for zip_path, old_url in parsed.asset_urls.items():
        data = parsed.assets.get(zip_path)
        if data is None:
            continue
        ext = _asset_extension(zip_path)
        content_type = ASSET_CONTENT_TYPES.get(ext, "application/octet-stream")
        try:
            new_url = await r2_service.upload_file(data, extension=ext, content_type=content_type, folder="restored")
        except Exception:
            failed += 1
            continue
        url_map[old_url] = new_url
        restored += 1
    return url_map, restored, failed


def _remap_urls(value: Any, url_map: Dict[str, str]) -> Any:
    if isinstance(value, str):
        return url_map.get(value, value)
    if isinstance(value, list):
        return [_remap_urls(v, url_map) for v in value]
    if isinstance(value, dict):
        return {k: _remap_urls(v, url_map) for k, v in value.items()}
    return value


SIMPLE_LIST_SECTIONS = {
    "products": "products",
    "categories": "categories",
    "hero": "hero_configs",
    "site-assets": "site_assets",
    "collection-slides": "collection_slides",
    "testimonials": "testimonials",
    "faq": "faq_items",
}

SINGLETON_SECTIONS = {
    "studio-settings": ("studio_settings", "settings_key", "main"),
    "shop-page": ("shop_page_settings", "settings_key", "main"),
    "home-page": ("home_page_settings", "settings_key", "main"),
    "story-page": ("story_page_settings", "settings_key", "main"),
    "navigation": ("navigation_settings", "settings_key", "main"),
    "contact-page": ("contact_page_settings", "settings_key", "main"),
    "history-page": ("history_page_settings", "settings_key", "main"),
    "product-page": ("product_page_settings", "settings_key", "main"),
}


def _object_id(raw: Any) -> ObjectId:
    if isinstance(raw, str):
        try:
            return ObjectId(raw)
        except InvalidId:
            pass
    return ObjectId()


async def _restore_list(database, collection_name: str, items: List[Dict[str, Any]]) -> None:
    collection = database[collection_name]
    for item in items:
        if not isinstance(item, dict):
            continue
        doc = dict(item)
        oid = _object_id(doc.pop("_id", None))
        await collection.replace_one({"_id": oid}, doc, upsert=True)


async def _restore_singleton(database, collection_name: str, key_field: str, key_value: str, value: Dict[str, Any]) -> None:
    doc = dict(value)
    doc.pop("_id", None)
    doc[key_field] = key_value
    await database[collection_name].replace_one({key_field: key_value}, doc, upsert=True)


async def _restore_section(key: str, value: Any, database, result: ImportResult) -> None:
    if key in SIMPLE_LIST_SECTIONS:
        if not isinstance(value, list):
            result.sections_skipped.append(key)
            result.sections_skip_reasons[key] = "invalid_shape"
            return
        await _restore_list(database, SIMPLE_LIST_SECTIONS[key], value)
        result.sections_restored.append(key)
        return

    if key in SINGLETON_SECTIONS:
        if not isinstance(value, dict):
            result.sections_skipped.append(key)
            result.sections_skip_reasons[key] = "invalid_shape"
            return
        collection_name, key_field, key_value = SINGLETON_SECTIONS[key]
        await _restore_singleton(database, collection_name, key_field, key_value, value)
        result.sections_restored.append(key)
        return

    if key == "policies" and isinstance(value, dict):
        meta = value.get("meta")
        if isinstance(meta, dict):
            await _restore_singleton(database, "policy_page_meta", "meta_key", "main", meta)
        sections = value.get("sections")
        if isinstance(sections, list):
            await _restore_list(database, "policy_sections", sections)
        result.sections_restored.append(key)
        return

    if key == "journal" and isinstance(value, dict):
        meta = value.get("meta")
        if isinstance(meta, dict):
            await _restore_singleton(database, "journal_page_settings", "settings_key", "main", meta)
        posts = value.get("data")
        if isinstance(posts, list):
            await _restore_list(database, "blog_posts", posts)
        result.sections_restored.append(key)
        return

    result.sections_skipped.append(key)
    result.sections_skip_reasons[key] = "unknown_section"


async def restore_bundle(parsed: ParsedBundle, database, r2_service) -> ImportResult:
    url_map, assets_restored, assets_failed = await _upload_assets(parsed, r2_service)
    sections = _remap_urls(parsed.sections, url_map)

    result = ImportResult(assets_restored=assets_restored, assets_failed=assets_failed)

    # Restore categories before products so product.categories FK references resolve.
    ordered_keys = sorted(sections.keys(), key=lambda k: 0 if k == "categories" else 1)
    for key in ordered_keys:
        value = sections[key]
        if isinstance(value, dict) and "__error" in value:
            result.sections_skipped.append(key)
            result.sections_skip_reasons[key] = "source_error"
            continue
        await _restore_section(key, value, database, result)

    await cache.delete_pattern("chokmoki:*")
    return result
