"""Unified per-order audit ledger — append-only, one document per event.

Every order-lifecycle mutation (creation, payment, status changes,
fulfillment, shipment updates, admin notes) appends here, so a single query
against `order_events` reconstructs the FULL history of an order — instead of
reading four disconnected places (the mutable orders collection, the one-shot
order_logs snapshot, the shipment-only history arrays, and the not-order-scoped
admin-audit log lines) and hoping none of them lost anything.

This is a plain synchronous Mongo insert, not routed through Redis Streams —
that durability guarantee is reserved for money-critical payment confirmation
(src/orders/consumer.py). Status/fulfillment/shipment/note changes here are
already fast, synchronous, admin- or webhook-triggered mutations with no
crash-loses-money risk, so queuing them would add latency with no real benefit.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from src.database.connection import db
from src.plugins.logger import logger

COLLECTION_NAME = "order_events"


async def ensure_indexes() -> None:
    database = await db.get_database()
    collection = database[COLLECTION_NAME]
    await collection.create_index([("order_id", 1), ("created_at", 1)])


async def append_event(
    order_id: str,
    event_type: str,
    actor: str,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """Append one ledger entry. Never raises — a ledger write failing must
    never break the actual mutation it's describing.
    """
    try:
        database = await db.get_database()
        collection = database[COLLECTION_NAME]
        await collection.insert_one(
            {
                "order_id": order_id,
                "event_type": event_type,
                "actor": actor,
                "detail": detail or {},
                "created_at": datetime.utcnow(),
            }
        )
    except Exception as e:
        if logger:
            logger.error(f"Failed to append order_events entry for {order_id} ({event_type}): {e}")


async def get_events(order_id: str) -> list[Dict[str, Any]]:
    database = await db.get_database()
    collection = database[COLLECTION_NAME]
    cursor = collection.find({"order_id": order_id}).sort("created_at", 1)
    events = await cursor.to_list(length=1000)
    for e in events:
        e["_id"] = str(e["_id"])
        if isinstance(e.get("created_at"), datetime):
            e["created_at"] = e["created_at"].isoformat()
    return events
