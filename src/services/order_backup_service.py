"""Export/restore the orders + order_logs collections as a standalone JSON
backup, independent of the site-content bundle (contentBundle.ts) which
deliberately excludes orders. Used to clone/restore order data across a
database wipe without touching site content.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.utils.mongo_json import MongoJSONEncoder

MAX_ORDERS_BACKUP_BYTES = 200 * 1024 * 1024  # 200MB — text-only JSON, no media

_ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class OrdersBackupParseError(ValueError):
    """Raised when the uploaded file is not a well-formed orders backup JSON."""


@dataclass
class ParsedOrdersBackup:
    orders: List[Dict[str, Any]] = field(default_factory=list)
    order_logs: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class OrdersImportResult:
    orders_restored: int = 0
    orders_skipped: int = 0
    order_logs_restored: int = 0
    order_logs_skipped: int = 0


@dataclass
class OrdersRestorePlan:
    orders_to_restore: int = 0
    order_logs_to_restore: int = 0


def _inflate_datetimes(value: Any) -> Any:
    """Recursively parse ISO-8601 datetime strings back into datetime objects
    so Mongo stores real dates (sortable/filterable), not plain strings."""
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


async def export_orders_backup(database) -> Dict[str, Any]:
    """Dump every order + order_log document. Returns a JSON-serializable dict
    (ObjectId/datetime already stringified via MongoJSONEncoder round-trip)."""
    orders = [doc async for doc in database["orders"].find({})]
    order_logs = [doc async for doc in database["order_logs"].find({})]
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "generator": "chokmoki-orders-backup",
        "orders": orders,
        "order_logs": order_logs,
    }
    # Round-trip through the Mongo-safe encoder so ObjectId/datetime become
    # plain strings before this dict is handed to a normal JSON response.
    return json.loads(json.dumps(payload, cls=MongoJSONEncoder))


def parse_orders_backup(raw: bytes) -> ParsedOrdersBackup:
    try:
        content = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise OrdersBackupParseError("Uploaded file is not valid JSON") from e

    if not isinstance(content, dict) or "orders" not in content:
        raise OrdersBackupParseError("Backup JSON is missing an 'orders' array")

    orders = content.get("orders")
    order_logs = content.get("order_logs", [])
    if not isinstance(orders, list):
        raise OrdersBackupParseError("'orders' must be a list")
    if not isinstance(order_logs, list):
        raise OrdersBackupParseError("'order_logs' must be a list")

    return ParsedOrdersBackup(
        orders=[_inflate_datetimes(o) for o in orders],
        order_logs=[_inflate_datetimes(o) for o in order_logs],
    )


def plan_orders_restore(parsed: ParsedOrdersBackup) -> OrdersRestorePlan:
    return OrdersRestorePlan(
        orders_to_restore=len(parsed.orders),
        order_logs_to_restore=len(parsed.order_logs),
    )


async def _restore_by_order_id(database, collection_name: str, docs: List[Dict[str, Any]]) -> int:
    collection = database[collection_name]
    restored = 0
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        order_id = doc.get("order_id")
        if not order_id:
            continue
        body = {k: v for k, v in doc.items() if k != "_id"}
        await collection.replace_one({"order_id": order_id}, body, upsert=True)
        restored += 1
    return restored


async def restore_orders_backup(parsed: ParsedOrdersBackup, database) -> OrdersImportResult:
    """Upsert by order_id (the business key, unique-indexed on both
    collections) rather than by Mongo _id, so a restore is safe regardless of
    whether the target DB is empty or already has some orders."""
    result = OrdersImportResult()
    result.orders_restored = await _restore_by_order_id(database, "orders", parsed.orders)
    result.orders_skipped = len(parsed.orders) - result.orders_restored
    result.order_logs_restored = await _restore_by_order_id(database, "order_logs", parsed.order_logs)
    result.order_logs_skipped = len(parsed.order_logs) - result.order_logs_restored
    return result
