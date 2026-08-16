"""Product inventory reservations, atomic decrements, and reconciliation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from src.config import settings
from src.database.connection import db
from src.database.redis_connection import redis_client
from src.models.order import ValidatedOrderItem
from src.plugins.logger import logger


@dataclass(frozen=True)
class ReservationLine:
    product_id: str
    quantity: int


class InventoryService:
    COLLECTION_NAME = "products"
    # Durable mirror of the Redis reservation key — see reserve_for_order()'s
    # comment for why this exists. TTL sized generously past
    # inventory_reservation_ttl_seconds (1h default) so there's a real window
    # to recover a reservation whose Redis key already expired, without
    # keeping resolved rows around forever.
    RESERVATIONS_COLLECTION = "inventory_reservations"
    RESERVATIONS_TTL_SECONDS = 7 * 24 * 3600
    RESERVATION_PREFIX = "inv:order:"
    PENDING_QTY_PREFIX = "inv:pending:"
    LOCK_PREFIX = "inv:lock:"
    LOCK_TTL_SECONDS = 5

    @property
    def reservation_ttl(self) -> int:
        return settings.inventory_reservation_ttl_seconds

    async def ensure_indexes(self) -> None:
        database = await db.get_database()
        collection = database[self.RESERVATIONS_COLLECTION]
        await collection.create_index("order_id", unique=True)
        await collection.create_index([("status", 1), ("created_at", 1)])
        await collection.create_index(
            "created_at", expireAfterSeconds=self.RESERVATIONS_TTL_SECONDS, name="created_at_ttl"
        )

    def tracks_inventory(self, stock_qty: Optional[int]) -> bool:
        if not settings.inventory_enabled:
            return False
        return stock_qty is not None

    @staticmethod
    def _pending_key(product_id: str) -> str:
        return f"{InventoryService.PENDING_QTY_PREFIX}{product_id}"

    @staticmethod
    def _reservation_key(order_id: str) -> str:
        return f"{InventoryService.RESERVATION_PREFIX}{order_id}"

    @staticmethod
    def _lock_key(product_id: str) -> str:
        return f"{InventoryService.LOCK_PREFIX}{product_id}"

    async def _get_stock_qty(self, product_id: str) -> Optional[int]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        filt: Dict[str, Any]
        if ObjectId.is_valid(product_id):
            filt = {"_id": ObjectId(product_id)}
        else:
            doc = await collection.find_one({"slug": product_id}, {"_id": 1})
            if not doc:
                return None
            filt = {"_id": doc["_id"]}

        doc = await collection.find_one(filt, {"stock_qty": 1})
        if not doc:
            return None
        value = doc.get("stock_qty")
        if value is None:
            return None
        return int(value)

    async def _acquire_product_lock(self, product_id: str) -> bool:
        redis = await redis_client.get_client()
        return bool(
            await redis.set(
                self._lock_key(product_id),
                "1",
                nx=True,
                ex=self.LOCK_TTL_SECONDS,
            )
        )

    async def _release_product_lock(self, product_id: str) -> None:
        redis = await redis_client.get_client()
        await redis.delete(self._lock_key(product_id))

    async def _get_pending_qty(self, product_id: str) -> int:
        redis = await redis_client.get_client()
        raw = await redis.get(self._pending_key(product_id))
        return int(raw or 0)

    async def _adjust_pending_qty(self, product_id: str, delta: int) -> None:
        redis = await redis_client.get_client()
        key = self._pending_key(product_id)
        if delta > 0:
            await redis.incrby(key, delta)
            return
        new_value = await redis.decrby(key, abs(delta))
        if new_value <= 0:
            await redis.delete(key)

    async def _atomic_decrement(self, product_id: str, quantity: int) -> bool:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        filt: Dict[str, Any]
        if ObjectId.is_valid(product_id):
            filt = {"_id": ObjectId(product_id)}
        else:
            doc = await collection.find_one({"slug": product_id}, {"_id": 1})
            if not doc:
                return False
            filt = {"_id": doc["_id"]}

        updated = await collection.find_one_and_update(
            {**filt, "stock_qty": {"$gte": quantity}},
            {"$inc": {"stock_qty": -quantity}},
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            return False

        if int(updated.get("stock_qty", 0)) <= 0:
            await collection.update_one(filt, {"$set": {"stock_status": "out_of_stock"}})
        else:
            await collection.update_one(filt, {"$set": {"stock_status": "in_stock"}})
        return True

    async def _sync_availability_status(self, product_id: str) -> None:
        try:
            stock_qty = await self._get_stock_qty(product_id)
            if not self.tracks_inventory(stock_qty):
                return
            pending = await self._get_pending_qty(product_id)
            available = int(stock_qty) - pending
            database = await db.get_database()
            collection = database[self.COLLECTION_NAME]
            if ObjectId.is_valid(product_id):
                filt: Dict[str, Any] = {"_id": ObjectId(product_id)}
            else:
                doc = await collection.find_one({"slug": product_id}, {"_id": 1})
                if not doc:
                    return
                filt = {"_id": doc["_id"]}
            status = "out_of_stock" if available <= 0 else "in_stock"
            await collection.update_one(filt, {"$set": {"stock_status": status}})
        except Exception as e:
            logger.warning(f"Inventory availability status sync failed for {product_id}: {e}")

    async def _reserve_product(self, product_id: str, quantity: int) -> None:
        stock_qty = await self._get_stock_qty(product_id)
        if not self.tracks_inventory(stock_qty):
            return

        if not await self._acquire_product_lock(product_id):
            raise ValueError(f"Inventory lock unavailable for product {product_id}")

        try:
            pending = await self._get_pending_qty(product_id)
            available = int(stock_qty) - pending
            if quantity > available:
                raise ValueError(f"Insufficient stock for product {product_id}")

            await self._adjust_pending_qty(product_id, quantity)
            await self._sync_availability_status(product_id)
        finally:
            await self._release_product_lock(product_id)

    async def reserve_for_order(
        self, order_id: str, items: List[ValidatedOrderItem]
    ) -> None:
        if not settings.inventory_enabled:
            return

        reserved: List[ReservationLine] = []
        redis = await redis_client.get_client()
        try:
            for item in items:
                stock_qty = await self._get_stock_qty(item.product_id)
                if not self.tracks_inventory(stock_qty):
                    continue
                await self._reserve_product(item.product_id, item.quantity)
                reserved.append(
                    ReservationLine(
                        product_id=item.product_id, quantity=item.quantity
                    )
                )

            if not reserved:
                return

            payload = json.dumps(
                [
                    {"product_id": line.product_id, "quantity": line.quantity}
                    for line in reserved
                ]
            )
            await redis.setex(
                self._reservation_key(order_id),
                self.reservation_ttl,
                payload,
            )
            # Durable mirror, independent of the Redis key's TTL — if that
            # key expires before commit_reservation/release_reservation runs
            # (e.g. a payment recovered hours later via reconciliation), this
            # is what lets the pending-quantity hold still get released
            # instead of leaking forever. See commit_reservation/
            # release_reservation/reconcile_stale_reservations below.
            database = await db.get_database()
            await database[self.RESERVATIONS_COLLECTION].update_one(
                {"order_id": order_id},
                {
                    "$setOnInsert": {
                        "order_id": order_id,
                        "lines": [
                            {"product_id": line.product_id, "quantity": line.quantity}
                            for line in reserved
                        ],
                        "status": "reserved",
                        "created_at": datetime.utcnow(),
                        "resolved_at": None,
                    }
                },
                upsert=True,
            )
        except Exception:
            for line in reserved:
                await self._adjust_pending_qty(line.product_id, -line.quantity)
            await redis.delete(self._reservation_key(order_id))
            raise

    async def _load_reservation(self, order_id: str) -> List[ReservationLine]:
        redis = await redis_client.get_client()
        raw = await redis.get(self._reservation_key(order_id))
        if not raw:
            return []
        data = json.loads(raw)
        return [
            ReservationLine(product_id=str(row["product_id"]), quantity=int(row["quantity"]))
            for row in data
        ]

    async def _resolve_durable_mirror(self, order_id: str, status: str) -> Optional[dict]:
        """Atomically mark the durable mirror resolved (committed/released)
        if it's still 'reserved' — a safe no-op if already resolved (by a
        concurrent caller or a prior run) or never written (inventory
        tracking disabled, or the order had no trackable lines). The atomic
        claim is what prevents double-processing if commit/release ever race
        on the same order.
        """
        database = await db.get_database()
        collection = database[self.RESERVATIONS_COLLECTION]
        return await collection.find_one_and_update(
            {"order_id": order_id, "status": "reserved"},
            {"$set": {"status": status, "resolved_at": datetime.utcnow()}},
            return_document=ReturnDocument.AFTER,
        )

    async def commit_reservation(self, order_id: str) -> None:
        lines = await self._load_reservation(order_id)
        from_mirror = None
        if not lines:
            from_mirror = await self._resolve_durable_mirror(order_id, "committed")
            if not from_mirror:
                return
            lines = [
                ReservationLine(product_id=str(l["product_id"]), quantity=int(l["quantity"]))
                for l in from_mirror["lines"]
            ]

        for line in lines:
            if not await self._atomic_decrement(line.product_id, line.quantity):
                logger.error(
                    f"Inventory commit failed for order {order_id} product {line.product_id}"
                )
                raise ValueError(f"Insufficient stock for product {line.product_id}")

        for line in lines:
            await self._adjust_pending_qty(line.product_id, -line.quantity)
        redis = await redis_client.get_client()
        await redis.delete(self._reservation_key(order_id))
        if from_mirror is None:
            # Redis path succeeded — still resolve the durable mirror so
            # reconcile_stale_reservations doesn't try to process it again.
            await self._resolve_durable_mirror(order_id, "committed")

    async def commit_items(self, items: List[ValidatedOrderItem]) -> None:
        if not settings.inventory_enabled:
            return

        for item in items:
            stock_qty = await self._get_stock_qty(item.product_id)
            if not self.tracks_inventory(stock_qty):
                continue
            if not await self._atomic_decrement(item.product_id, item.quantity):
                raise ValueError(f"Insufficient stock for product {item.product_id}")

    async def release_committed_items(self, items: List[ValidatedOrderItem]) -> None:
        """Reverse commit_items() when the following order write never landed."""
        if not settings.inventory_enabled:
            return
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        for item in items:
            stock_qty = await self._get_stock_qty(item.product_id)
            if not self.tracks_inventory(stock_qty):
                continue
            filt: Dict[str, Any]
            if ObjectId.is_valid(item.product_id):
                filt = {"_id": ObjectId(item.product_id)}
            else:
                doc = await collection.find_one({"slug": item.product_id}, {"_id": 1})
                if not doc:
                    continue
                filt = {"_id": doc["_id"]}
            await collection.update_one(
                filt,
                {"$inc": {"stock_qty": item.quantity}, "$set": {"stock_status": "in_stock"}},
            )

    async def release_reservation(self, order_id: str) -> None:
        lines = await self._load_reservation(order_id)
        from_mirror = None
        if not lines:
            from_mirror = await self._resolve_durable_mirror(order_id, "released")
            if not from_mirror:
                return
            lines = [
                ReservationLine(product_id=str(l["product_id"]), quantity=int(l["quantity"]))
                for l in from_mirror["lines"]
            ]

        for line in lines:
            await self._adjust_pending_qty(line.product_id, -line.quantity)
            await self._sync_availability_status(line.product_id)
        redis = await redis_client.get_client()
        await redis.delete(self._reservation_key(order_id))
        if from_mirror is None:
            await self._resolve_durable_mirror(order_id, "released")

    async def reconcile_stale_reservations(self) -> int:
        redis = await redis_client.get_client()
        released = 0
        async for key in redis.scan_iter(match=f"{self.RESERVATION_PREFIX}*"):
            ttl = await redis.ttl(key)
            if ttl == -2:
                continue
            if ttl > 60:
                continue
            order_id = key.removeprefix(self.RESERVATION_PREFIX)
            await self.release_reservation(order_id)
            released += 1

        # Redis SCAN above only sees keys that still exist. Once a
        # reservation key's TTL (inventory_reservation_ttl_seconds) has
        # fully expired, it's invisible to that loop even though its
        # pending-quantity hold on stock was never released — this is
        # exactly the leak the durable mirror exists to close. Sweep it for
        # anything still "reserved" past when its Redis key should have
        # expired.
        database = await db.get_database()
        collection = database[self.RESERVATIONS_COLLECTION]
        cutoff = datetime.utcnow() - timedelta(seconds=self.reservation_ttl)
        async for doc in collection.find({"status": "reserved", "created_at": {"$lt": cutoff}}):
            await self.release_reservation(doc["order_id"])
            released += 1
        return released
