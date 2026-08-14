"""Parse and restore a site-content backup ZIP produced by
aurum-editorial/src/lib/contentBundle.ts (exportAllContentBundle).

The ZIP also carries an orders/ folder (orders.json + order_logs.json, plain
JSON arrays) alongside products/ and sections/ — one export, one ZIP, one
restore endpoint for the whole backend. Orders/order_logs are restored via
order_backup_service's upsert-by-order_id logic, never wiped or replaced.
"""
from __future__ import annotations

import csv
import hashlib
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
    orders: List[Dict[str, Any]] = field(default_factory=list)
    order_logs: List[Dict[str, Any]] = field(default_factory=list)


def _replace_relative_paths(
    value: Any,
    base_path: str,
    manifest: Dict[str, Dict[str, str]],
) -> Any:
    """Replace relative image paths (e.g. 'images/thumbnail.jpg') with the
    original source URL from manifest.csv.  base_path is the entity's
    folder path inside the ZIP (e.g. 'products/ganges-pearl-drop')."""
    if isinstance(value, str) and value.startswith("images/"):
        full_zip_path = f"{base_path}/{value}"
        row = manifest.get(full_zip_path, {})
        original_url = row.get("Original Source URL", "")
        if original_url:
            return original_url
        return value
    if isinstance(value, list):
        return [_replace_relative_paths(v, base_path, manifest) for v in value]
    if isinstance(value, dict):
        return {k: _replace_relative_paths(v, base_path, manifest) for k, v in value.items()}
    return value


def _section_key_from_json(content: dict) -> str | None:
    """Extract the section key from a per-entity content.json (the first key
    that is not 'exported_at' or 'generator')."""
    for k in content:
        if k not in ("exported_at", "generator"):
            return k
    return None


def parse_bundle_zip(raw: bytes) -> ParsedBundle:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise BundleParseError("Uploaded file is not a valid ZIP archive") from e

    names = set(zf.namelist())

    # Manifest is required.
    if "manifest.csv" not in names:
        raise BundleParseError("Bundle is missing manifest.csv")

    # Read manifest: zip_path -> row
    manifest_text = zf.read("manifest.csv").decode("utf-8-sig")
    manifest: Dict[str, Dict[str, str]] = {}
    for row in csv.DictReader(io.StringIO(manifest_text)):
        manifest[row["Path in ZIP"]] = row

    sections: Dict[str, Any] = {}
    asset_urls: Dict[str, str] = {}
    assets: Dict[str, bytes] = {}
    products: list[Any] = []
    orders: list[Any] = []
    order_logs: list[Any] = []

    for name in names:
        if name == "orders/orders.json":
            try:
                parsed_orders = json.loads(zf.read(name).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise BundleParseError("orders/orders.json is not valid JSON") from e
            if not isinstance(parsed_orders, list):
                raise BundleParseError("orders/orders.json must be a JSON array")
            orders = [_inflate_order_datetimes(o) for o in parsed_orders]
            continue

        if name == "orders/order_logs.json":
            try:
                parsed_logs = json.loads(zf.read(name).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise BundleParseError("orders/order_logs.json is not valid JSON") from e
            if not isinstance(parsed_logs, list):
                raise BundleParseError("orders/order_logs.json must be a JSON array")
            order_logs = [_inflate_order_datetimes(o) for o in parsed_logs]
            continue

        if not name.endswith("/content.json"):
            # Collect images from manifest
            if "/images/" in name:
                row = manifest.get(name, {})
                if row.get("Status") == "downloaded":
                    url = row.get("Original Source URL", "")
                    if url:
                        asset_urls[name] = url
                        try:
                            assets[name] = zf.read(name)
                        except KeyError:
                            pass
            continue

        dir_path = name.rsplit("/", 1)[0]  # e.g. "products/foo" or "sections/hero"

        try:
            content = json.loads(zf.read(name).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        section_key = _section_key_from_json(content)
        if section_key is None:
            continue

        value = content[section_key]

        # Inflate relative image paths back to original URLs.
        value = _replace_relative_paths(value, dir_path, manifest)

        if name.startswith("products/"):
            products.append(value)
        elif name.startswith("sections/"):
            sections[section_key] = value

    if products:
        sections["products"] = products

    return ParsedBundle(sections=sections, assets=assets, asset_urls=asset_urls, orders=orders, order_logs=order_logs)


from bson import ObjectId
from bson.errors import InvalidId

from src.services.cache_service import cache
from src.services.order_backup_service import (
    OrdersImportResult,
    ParsedOrdersBackup,
    _inflate_datetimes as _inflate_order_datetimes,
    restore_orders_backup,
)


@dataclass
class ImportResult:
    sections_restored: List[str] = field(default_factory=list)
    sections_skipped: List[str] = field(default_factory=list)
    sections_skip_reasons: Dict[str, str] = field(default_factory=dict)
    assets_restored: int = 0
    assets_failed: int = 0
    assets_deduplicated: int = 0
    orders_restored: int = 0
    orders_skipped: int = 0
    order_logs_restored: int = 0
    order_logs_skipped: int = 0


def _asset_extension(zip_path: str) -> str:
    if "." not in zip_path:
        return "bin"
    return zip_path.rsplit(".", 1)[-1].lower()


async def _upload_assets(parsed: ParsedBundle, r2_service) -> tuple[Dict[str, str], int, int, int]:
    """Upload every bundled asset to R2, deduplicating identical bytes within this
    run by sha256 hash so a repeated restore of the same backup doesn't create
    duplicate R2 objects. Returns (old_url -> new_url map, restored, failed, deduplicated).
    """
    url_map: Dict[str, str] = {}
    hash_to_new_url: Dict[str, str] = {}
    restored = 0
    failed = 0
    deduplicated = 0
    for zip_path, old_url in parsed.asset_urls.items():
        data = parsed.assets.get(zip_path)
        if data is None:
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in hash_to_new_url:
            url_map[old_url] = hash_to_new_url[digest]
            restored += 1
            deduplicated += 1
            continue
        ext = _asset_extension(zip_path)
        content_type = ASSET_CONTENT_TYPES.get(ext, "application/octet-stream")
        try:
            new_url = await r2_service.upload_file(data, extension=ext, content_type=content_type, folder="restored")
        except Exception:
            failed += 1
            continue
        hash_to_new_url[digest] = new_url
        url_map[old_url] = new_url
        restored += 1
    return url_map, restored, failed, deduplicated


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
    "account-page": ("account_page_settings", "settings_key", "main"),
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


# (collection_name, field, unique) — scoped to the 17 restore collections only.
# Mirrors the lookup patterns the existing service layer relies on (slug lookups
# for products/categories, settings_key/meta_key upserts for singletons).
RESTORE_INDEXES: List[tuple[str, str, bool]] = [
    ("products", "slug", True),
    ("categories", "slug", True),
    ("blog_posts", "slug", True),
    ("studio_settings", "settings_key", True),
    ("shop_page_settings", "settings_key", True),
    ("home_page_settings", "settings_key", True),
    ("story_page_settings", "settings_key", True),
    ("navigation_settings", "settings_key", True),
    ("contact_page_settings", "settings_key", True),
    ("account_page_settings", "settings_key", True),
    ("history_page_settings", "settings_key", True),
    ("product_page_settings", "settings_key", True),
    ("journal_page_settings", "settings_key", True),
    ("policy_page_meta", "meta_key", True),
]


async def ensure_restore_indexes(database) -> None:
    for collection_name, field_name, unique in RESTORE_INDEXES:
        await database[collection_name].create_index(field_name, unique=unique)


async def restore_bundle(parsed: ParsedBundle, database, r2_service) -> ImportResult:
    url_map, assets_restored, assets_failed, assets_deduplicated = await _upload_assets(parsed, r2_service)
    sections = _remap_urls(parsed.sections, url_map)

    result = ImportResult(
        assets_restored=assets_restored,
        assets_failed=assets_failed,
        assets_deduplicated=assets_deduplicated,
    )

    # Restore categories before products so product.categories FK references resolve.
    ordered_keys = sorted(sections.keys(), key=lambda k: 0 if k == "categories" else 1)
    for key in ordered_keys:
        value = sections[key]
        if isinstance(value, dict) and "__error" in value:
            result.sections_skipped.append(key)
            result.sections_skip_reasons[key] = "source_error"
            continue
        await _restore_section(key, value, database, result)

    if parsed.orders or parsed.order_logs:
        orders_result = await restore_orders_backup(
            ParsedOrdersBackup(orders=parsed.orders, order_logs=parsed.order_logs), database
        )
        result.orders_restored = orders_result.orders_restored
        result.orders_skipped = orders_result.orders_skipped
        result.order_logs_restored = orders_result.order_logs_restored
        result.order_logs_skipped = orders_result.order_logs_skipped

    await cache.delete_pattern("chokmoki:*")
    await ensure_restore_indexes(database)
    return result


@dataclass
class RestorePlan:
    sections_to_restore: List[str] = field(default_factory=list)
    sections_skipped: List[str] = field(default_factory=list)
    sections_skip_reasons: Dict[str, str] = field(default_factory=dict)
    assets_to_upload: int = 0
    id_diff: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)  # section -> {"new": [...], "overwriting": [...]}
    orders_to_restore: int = 0
    order_logs_to_restore: int = 0


async def plan_restore(parsed: ParsedBundle, database) -> RestorePlan:
    plan = RestorePlan(
        assets_to_upload=len(parsed.assets),
        orders_to_restore=len(parsed.orders),
        order_logs_to_restore=len(parsed.order_logs),
    )

    for key, value in parsed.sections.items():
        if isinstance(value, dict) and "__error" in value:
            plan.sections_skipped.append(key)
            plan.sections_skip_reasons[key] = "source_error"
            continue
        if key in SIMPLE_LIST_SECTIONS and isinstance(value, list):
            plan.sections_to_restore.append(key)
            await _diff_list_ids(database, SIMPLE_LIST_SECTIONS[key], key, value, plan)
        elif key in SINGLETON_SECTIONS and isinstance(value, dict):
            plan.sections_to_restore.append(key)
        elif key == "policies" and isinstance(value, dict):
            plan.sections_to_restore.append(key)
            sections = value.get("sections")
            if isinstance(sections, list):
                await _diff_list_ids(database, "policy_sections", key, sections, plan)
        elif key == "journal" and isinstance(value, dict):
            plan.sections_to_restore.append(key)
            posts = value.get("data")
            if isinstance(posts, list):
                await _diff_list_ids(database, "blog_posts", key, posts, plan)
        else:
            plan.sections_skipped.append(key)
            plan.sections_skip_reasons[key] = "invalid_shape" if key in SIMPLE_LIST_SECTIONS or key in SINGLETON_SECTIONS else "unknown_section"

    return plan


async def _diff_list_ids(database, collection_name: str, section_key: str, items: List[Dict[str, Any]], plan: RestorePlan) -> None:
    new_ids: List[str] = []
    overwriting_ids: List[str] = []
    collection = database[collection_name]
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("_id")
        oid = _object_id(raw_id) if raw_id else None
        existing = await collection.find_one({"_id": oid}) if oid is not None else None
        target = overwriting_ids if existing else new_ids
        target.append(str(oid) if oid is not None else "(new)")
    plan.id_diff[section_key] = {"new": new_ids, "overwriting": overwriting_ids}
