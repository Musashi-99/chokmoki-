"""Raw full-collection JSON export/import for cloning the whole database
across a Docker volume wipe.

Two independent, non-overlapping bundles:
  - config:  every content collection EXCEPT orders/order_logs
  - orders:  orders + order_logs only

Collection names are validated against an allow-list on both export and
import so orders can never be touched by the config endpoints (and vice
versa). This is deliberately separate from src/services/import_service.py
(the asset-aware ZIP bundle restore) — that one remaps image URLs and is
upsert-only by design; this one is a plain data clone that also supports a
destructive wipe mode for restoring into an empty database.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from bson import ObjectId
from bson.errors import InvalidId

from src.utils.mongo_json import MongoJSONEncoder

CONFIG_SCHEMA_VERSION = "chokmoki-config-backup-v1"
ORDERS_SCHEMA_VERSION = "chokmoki-orders-backup-v1"

MAX_BACKUP_BYTES = 200 * 1024 * 1024  # 200MB — text-only JSON, no media

# Every collection restorable via /api/admin/import/config. orders/order_logs
# are intentionally absent so they can never be reached through this path.
CONFIG_COLLECTIONS: List[str] = [
    "products",
    "categories",
    "testimonials",
    "hero_configs",
    "site_assets",
    "faq_items",
    "collection_slides",
    "home_page_settings",
    "story_page_settings",
    "shop_page_settings",
    "studio_settings",
    "policy_page_meta",
    "policy_sections",
    "navigation_settings",
    "contact_page_settings",
    "history_page_settings",
    "product_page_settings",
    "blog_posts",
    "journal_page_settings",
    "contact_submissions",
    "newsletter_subscriptions",
]

ORDERS_COLLECTIONS: List[str] = ["orders", "order_logs"]

# Natural unique key per collection for merge-mode upserts. Collections not
# listed here fall back to upserting by _id.
KEY_FIELDS: Dict[str, str] = {
    "products": "slug",
    "categories": "slug",
    "blog_posts": "slug",
    "site_assets": "key",
    "policy_sections": "slug",
    "home_page_settings": "settings_key",
    "story_page_settings": "settings_key",
    "shop_page_settings": "settings_key",
    "studio_settings": "settings_key",
    "navigation_settings": "settings_key",
    "contact_page_settings": "settings_key",
    "history_page_settings": "settings_key",
    "product_page_settings": "settings_key",
    "journal_page_settings": "settings_key",
    "policy_page_meta": "meta_key",
}

_ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class BackupParseError(ValueError):
    """Raised when an uploaded backup file is not well-formed JSON, or a
    collection payload inside it isn't a list."""


class BackupVersionError(ValueError):
    """Raised when a backup's meta.schema doesn't match what this server
    currently expects."""


@dataclass
class BackupImportResult:
    mode: str
    restored: Dict[str, int] = field(default_factory=dict)
    skipped: Dict[str, int] = field(default_factory=dict)


@dataclass
class BackupRestorePlan:
    mode: str
    counts: Dict[str, int] = field(default_factory=dict)


def _object_id(raw: Any) -> ObjectId:
    if isinstance(raw, str):
        try:
            return ObjectId(raw)
        except InvalidId:
            pass
    return ObjectId()


def _inflate_datetimes(value: Any) -> Any:
    """Recursively parse ISO-8601 datetime strings back into datetime
    objects so Mongo stores real dates, not plain strings."""
    if isinstance(value, str) and _ISO_DATETIME_RE.match(value):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            return value
    if isinstance(value, list):
        return [_inflate_datetimes(v) for v in value]
    if isinstance(value, dict):
        return {k: _inflate_datetimes(v) for k, v in value.items()}
    return value


async def _export_collections(
    database,
    db_name: str,
    schema_version: str,
    generator: str,
    collection_names: List[str],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "meta": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "db_name": db_name,
            "schema": schema_version,
            "generator": generator,
        }
    }
    for name in collection_names:
        payload[name] = [doc async for doc in database[name].find({})]
    # Round-trip through the Mongo-safe encoder so ObjectId/datetime become
    # plain JSON-safe strings before this dict is handed to a JSON response.
    return json.loads(json.dumps(payload, cls=MongoJSONEncoder))


async def export_config(database, db_name: str) -> Dict[str, Any]:
    return await _export_collections(
        database, db_name, CONFIG_SCHEMA_VERSION, "chokmoki-config-backup", CONFIG_COLLECTIONS
    )


async def export_orders(database, db_name: str) -> Dict[str, Any]:
    return await _export_collections(
        database, db_name, ORDERS_SCHEMA_VERSION, "chokmoki-orders-backup", ORDERS_COLLECTIONS
    )


def _parse_backup(
    raw: bytes,
    expected_schema: str,
    allowed_collections: List[str],
) -> Dict[str, List[Dict[str, Any]]]:
    try:
        content = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise BackupParseError("Uploaded file is not valid JSON") from e

    if not isinstance(content, dict):
        raise BackupParseError("Backup JSON must be an object")

    meta = content.get("meta")
    schema = meta.get("schema") if isinstance(meta, dict) else None
    if schema != expected_schema:
        raise BackupVersionError(
            f"Backup schema mismatch: expected '{expected_schema}', got '{schema!r}'. "
            "Export a fresh backup from a matching server version."
        )

    collections: Dict[str, List[Dict[str, Any]]] = {}
    # Only allow-listed collection keys are ever read from the file — any
    # other top-level key (including "orders"/"order_logs" inside a config
    # file) is silently ignored, never reaching the database.
    for name in allowed_collections:
        items = content.get(name)
        if items is None:
            continue
        if not isinstance(items, list):
            raise BackupParseError(f"'{name}' must be a list")
        collections[name] = [_inflate_datetimes(item) for item in items if isinstance(item, dict)]
    return collections


def parse_config_backup(raw: bytes) -> Dict[str, List[Dict[str, Any]]]:
    if len(raw) > MAX_BACKUP_BYTES:
        raise BackupParseError(f"Backup exceeds maximum size of {MAX_BACKUP_BYTES // (1024 * 1024)}MB")
    return _parse_backup(raw, CONFIG_SCHEMA_VERSION, CONFIG_COLLECTIONS)


def parse_orders_backup(raw: bytes) -> Dict[str, List[Dict[str, Any]]]:
    if len(raw) > MAX_BACKUP_BYTES:
        raise BackupParseError(f"Backup exceeds maximum size of {MAX_BACKUP_BYTES // (1024 * 1024)}MB")
    return _parse_backup(raw, ORDERS_SCHEMA_VERSION, ORDERS_COLLECTIONS)


def plan_restore(collections: Dict[str, List[Dict[str, Any]]], mode: str) -> BackupRestorePlan:
    return BackupRestorePlan(mode=mode, counts={name: len(items) for name, items in collections.items()})


async def _wipe_and_insert(database, collections: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
    restored: Dict[str, int] = {}
    for name, items in collections.items():
        collection = database[name]
        await collection.delete_many({})
        docs = []
        for item in items:
            doc = dict(item)
            doc["_id"] = _object_id(doc.get("_id"))
            docs.append(doc)
        if docs:
            await collection.insert_many(docs)
        restored[name] = len(docs)
    return restored


async def _merge_upsert(database, collections: Dict[str, List[Dict[str, Any]]]) -> tuple[Dict[str, int], Dict[str, int]]:
    restored: Dict[str, int] = {}
    skipped: Dict[str, int] = {}
    for name, items in collections.items():
        collection = database[name]
        key_field = KEY_FIELDS.get(name, "_id")
        n_restored = 0
        n_skipped = 0
        for item in items:
            doc = dict(item)
            if key_field == "_id":
                oid = _object_id(doc.pop("_id", None))
                await collection.replace_one({"_id": oid}, doc, upsert=True)
                n_restored += 1
                continue
            key_value = doc.get(key_field)
            if not key_value:
                n_skipped += 1
                continue
            doc.pop("_id", None)
            await collection.replace_one({key_field: key_value}, doc, upsert=True)
            n_restored += 1
        restored[name] = n_restored
        if n_skipped:
            skipped[name] = n_skipped
    return restored, skipped


async def import_backup(database, collections: Dict[str, List[Dict[str, Any]]], mode: str) -> BackupImportResult:
    if mode not in ("wipe", "merge"):
        raise ValueError(f"Unknown import mode: {mode!r}")

    if mode == "wipe":
        restored = await _wipe_and_insert(database, collections)
        return BackupImportResult(mode=mode, restored=restored)

    restored, skipped = await _merge_upsert(database, collections)
    return BackupImportResult(mode=mode, restored=restored, skipped=skipped)
