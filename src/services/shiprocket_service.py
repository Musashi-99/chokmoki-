"""Shiprocket orchestration: order-to-payload mapping, courier quoting and
selection, the "Ready to Ship" pipeline, and webhook handling.

Raw HTTP calls live in src/shiprocket/client.py — this file only knows about
our own Order documents and how to map them to/from Shiprocket's shapes.
Operates on raw Mongo dicts rather than the Order Pydantic model since it
reads/writes the orders collection directly (same style as OrderService).
"""
from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.config import settings
from src.database.connection import db
from src.database.redis_connection import redis_client
from src.plugins.logger import logger
from src.services.product_service import ProductService
from src.services import order_ledger
from src.shiprocket.client import ShiprocketAPIError, ShiprocketClient, ShiprocketNotConfiguredError

# Optional alerts import (matches the established pattern in order_service.py)
try:
    from src.alerts.events import EVENT_SHIPMENT_UPDATE, publish_alert
except ImportError:
    EVENT_SHIPMENT_UPDATE = "shipment.updated"
    publish_alert = None


# Shiprocket's granular current_status strings -> our smaller shipment_status
# enum. Matched case-insensitively. Shiprocket has 20-30+ distinct status
# strings across its lifecycle/NDR/RTO flows — this list is NOT exhaustive.
# An unrecognized status must never regress the state machine (see
# _map_status below): silently defaulting to "pending" previously caused a
# shipment that already reached "AWB Assigned" to visibly roll back to
# "Pending" the moment Shiprocket sent a status we hadn't mapped yet
# (confirmed live with "Cancellation Requested").
_STATUS_MAP = {
    "awb assigned": "awb_assigned",
    "pickup scheduled": "pickup_scheduled",
    "pickup generated": "pickup_scheduled",
    "manifest generated": "pickup_scheduled",
    "pickup rescheduled": "pickup_scheduled",
    "picked up": "picked_up",
    "shipped": "picked_up",
    "in transit": "in_transit",
    "reached at destination hub": "in_transit",
    "reached destination hub": "in_transit",
    "out for delivery": "out_for_delivery",
    "delivered": "delivered",
    "rto initiated": "rto_initiated",
    "rto in transit": "rto_initiated",
    "rto delivered": "rto_delivered",
    "cancellation requested": "cancellation_requested",
    "cancelled": "cancelled",
    "cancelled shipment": "cancelled",
    "lost": "failed",
    "damaged": "failed",
    "undelivered": "failed",
}


def _map_status(raw_status: str) -> Optional[str]:
    """None means "unrecognized" — callers must keep the previous status
    rather than guessing, since Shiprocket's status vocabulary is larger
    than this table and will keep growing.
    """
    mapped = _STATUS_MAP.get((raw_status or "").strip().lower())
    if mapped is None and logger:
        logger.warning(f"Shiprocket: unrecognized status '{raw_status}', keeping previous shipment_status")
    return mapped


class ShiprocketService:
    COLLECTION_NAME = "orders"

    def __init__(self) -> None:
        if not settings.shiprocket_enabled:
            raise ShiprocketNotConfiguredError("Shiprocket integration is disabled (SHIPROCKET_ENABLED=false)")
        if not settings.shiprocket_pickup_location or not settings.shiprocket_pickup_pincode:
            raise ShiprocketNotConfiguredError(
                "SHIPROCKET_PICKUP_LOCATION / SHIPROCKET_PICKUP_PINCODE are not configured"
            )
        self.client = ShiprocketClient()

    async def _collection(self):
        database = await db.get_database()
        return database[self.COLLECTION_NAME]

    async def _append_status_history(self, order_id: str, status: str, raw_status: str) -> None:
        collection = await self._collection()
        entry = {
            "status": status,
            "raw_status": raw_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await collection.update_one({"order_id": order_id}, {"$push": {"shipment_status_history": entry}})
        # Single choke point for all 4 shipment-status transitions (AWB
        # assigned, pickup scheduled, webhook/track updates, cancel) — mirrors
        # into the unified order_events ledger alongside the existing
        # shipment-specific history array (additive, doesn't touch that array).
        actor = "admin" if raw_status in ("AWB Assigned", "Pickup scheduled", "Cancelled by admin") else "shiprocket_webhook"
        await order_ledger.append_event(
            order_id, "shipment_status_changed", actor, {"status": status, "raw_status": raw_status},
        )

    async def _record_scans(self, order_id: str, scans: List[Dict[str, Any]]) -> None:
        """Persist Shiprocket's raw courier scan events (date/activity/location).
        Webhooks and track-by-awb both resend the full cumulative list each
        time, so de-dupe by (date, activity) before appending anything new.
        """
        if not scans:
            return
        collection = await self._collection()
        order_doc = await collection.find_one({"order_id": order_id}, {"shipment_scans": 1})
        existing = (order_doc or {}).get("shipment_scans") or []
        seen = {(e.get("date"), e.get("activity")) for e in existing}
        new_entries = []
        for s in scans:
            date = s.get("date") or s.get("scan_date") or ""
            activity = s.get("activity") or s.get("status") or s.get("sr-status-label") or ""
            location = s.get("location") or ""
            key = (date, activity)
            if key in seen or not activity:
                continue
            seen.add(key)
            new_entries.append({"date": date, "activity": activity, "location": location})
        if new_entries:
            await collection.update_one(
                {"order_id": order_id}, {"$push": {"shipment_scans": {"$each": new_entries}}}
            )
        if logger:
            logger.info(
                f"Shiprocket scans for order {order_id}: received={len(scans)} "
                f"new={len(new_entries)} already_seen={len(scans) - len(new_entries)}"
            )

    async def _apply_status_update(
        self,
        order_id: str,
        raw_status: str,
        scans: Optional[List[Dict[str, Any]]] = None,
        awb: Optional[str] = None,
        courier_name: Optional[str] = None,
    ) -> Optional[str]:
        """Shared by handle_webhook() and track(): map + persist the current
        status, only appending a shipment_status_history entry when the
        status actually changed (webhooks/track resend the same status
        repeatedly — don't spam duplicate history entries).
        """
        collection = await self._collection()
        order_doc = await collection.find_one({"order_id": order_id})
        if not order_doc:
            if logger:
                logger.warning(f"Shiprocket: unknown order_id={order_id}")
            return None

        previous_status = order_doc.get("shipment_status", "pending")
        mapped_status = _map_status(raw_status) if raw_status else previous_status
        if mapped_status is None:
            # Unrecognized status string — keep the current status rather
            # than guessing/regressing. Still record scans so the raw event
            # isn't lost, just don't let it corrupt the tracked lifecycle stage.
            if scans:
                await self._record_scans(order_id, scans)
            return previous_status

        # A terminal state (cancelled/delivered/etc) must not be clobbered by
        # a stale, out-of-order courier update arriving after the fact (e.g.
        # a delayed "in transit" webhook landing after an admin cancellation)
        # — that's exactly the kind of state-machine inconsistency to avoid.
        if self._is_terminal_shipment_status(previous_status) and mapped_status != previous_status:
            if logger:
                logger.warning(
                    f"Shiprocket: ignoring stale status '{mapped_status}' for order {order_id} — "
                    f"already terminal at '{previous_status}'"
                )
            if scans:
                await self._record_scans(order_id, scans)
            return previous_status

        changed = mapped_status != previous_status

        if logger:
            logger.info(
                f"Shiprocket status update for order {order_id}: raw_status={raw_status!r} "
                f"mapped={mapped_status} previous={order_doc.get('shipment_status')} changed={changed}"
            )

        update_fields: Dict[str, Any] = {"shipment_status": mapped_status}
        if awb and not order_doc.get("awb_code"):
            update_fields["awb_code"] = awb
        if courier_name and not order_doc.get("courier_name"):
            update_fields["courier_name"] = courier_name
        await collection.update_one({"order_id": order_id}, {"$set": update_fields})

        if changed:
            await self._append_status_history(order_id, mapped_status, raw_status)
            if logger:
                logger.info(f"Shiprocket shipment_status_history appended for order {order_id}: {mapped_status}")
            await self._sync_order_status_type(order_id, mapped_status, order_doc.get("status", {}))
        if scans:
            await self._record_scans(order_id, scans)

        if changed and publish_alert:
            await publish_alert(
                EVENT_SHIPMENT_UPDATE,
                {
                    "order_id": order_id,
                    "status": mapped_status,
                    "raw_status": raw_status,
                    "awb_code": awb or order_doc.get("awb_code"),
                    "courier_name": courier_name or order_doc.get("courier_name"),
                },
            )
        return mapped_status

    # Courier shipment_status values that also exist as literal order status.type
    # values — Shiprocket confirming these should be reflected in the order's
    # main dashboard status too, not just the separate shipment_status field
    # (previously these lived in total isolation: an order could sit
    # "Accepted" in the main list forever even after Shiprocket confirmed
    # delivery, because nothing ever wrote the corresponding status.type).
    _SHIPMENT_TO_ORDER_STATUS_TYPE = {
        "out_for_delivery": "out_for_delivery",
        "delivered": "delivered",
    }

    async def _sync_order_status_type(
        self, order_id: str, mapped_shipment_status: str, current_status: Dict[str, Any]
    ) -> None:
        target_type = self._SHIPMENT_TO_ORDER_STATUS_TYPE.get(mapped_shipment_status)
        if not target_type or current_status.get("type") == target_type:
            return
        # Never downgrade an order a human has already terminally resolved
        # (e.g. admin explicitly rejected it) — courier confirmation should
        # only ever move the main status forward, not override a decision.
        if current_status.get("type") in ("rejected", "rejected_by_user"):
            return
        collection = await self._collection()
        await collection.update_one(
            {"order_id": order_id},
            {"$set": {"status": {"type": target_type, "reason": "Auto-updated from Shiprocket tracking", "extras": {}}}},
        )
        if logger:
            logger.info(f"Shiprocket: order {order_id} status.type synced to '{target_type}'")

    async def _order_package_dims(self, order_doc: Dict[str, Any]) -> tuple:
        """Real per-product weight/dimensions where set, config defaults only
        as a per-item fallback (never as a floor over known real data) —
        light jewelry must be able to report its actual sub-default weight.
        """
        product_service = ProductService()
        total_grams = 0.0
        missing_weight_items = []
        max_length = max_breadth = max_height = 0.0
        for item in order_doc.get("items", []):
            qty = item.get("quantity", 1)
            product = await product_service.get_by_id(item.get("product_id", ""))
            if product and product.weight_grams:
                total_grams += product.weight_grams * qty
            else:
                missing_weight_items.append(item.get("product_id"))
                total_grams += settings.shiprocket_default_weight_kg * 1000 * qty
            if product and product.package_length_cm and product.package_breadth_cm and product.package_height_cm:
                max_length = max(max_length, product.package_length_cm)
                max_breadth = max(max_breadth, product.package_breadth_cm)
                max_height = max(max_height, product.package_height_cm)

        if missing_weight_items and logger:
            logger.warning(
                f"Shiprocket: order {order_doc.get('order_id')} has product(s) with no "
                f"weight_grams set ({missing_weight_items}) — using default fallback for those"
            )

        # A real-but-tiny weight can round to 0.000kg, which couriers reject
        # outright — floor at 10g rather than silently shipping "0 weight".
        weight_kg = max(round(total_grams / 1000.0, 3), 0.01)
        length = max_length or settings.shiprocket_default_length_cm
        breadth = max_breadth or settings.shiprocket_default_breadth_cm
        height = max_height or settings.shiprocket_default_height_cm
        return weight_kg, length, breadth, height

    @staticmethod
    def _gst_rate_value():
        """Total GST % (cgst + sgst) for the order-item `tax` field.
        Shiprocket documents `tax` as an integer, so send a clean int when
        the total is whole (3.0 -> 3) and only fall back to the float for
        a genuinely fractional configured rate.
        """
        total = settings.gst_total_percent
        return int(total) if float(total).is_integer() else total

    def _build_create_order_payload(
        self, order_doc: Dict[str, Any], weight_kg: float, length_cm: float, breadth_cm: float, height_cm: float
    ) -> Dict[str, Any]:
        addr = order_doc.get("shipping_address", {})
        payment_method = "COD" if order_doc.get("payment_method") == "cod" else "Prepaid"
        order_date = order_doc.get("created_at")
        order_date_str = (
            order_date.strftime("%Y-%m-%d %H:%M")
            if isinstance(order_date, datetime)
            else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        )
        return {
            "order_id": order_doc["order_id"],
            "order_date": order_date_str,
            "pickup_location": settings.shiprocket_pickup_location,
            "billing_customer_name": addr.get("full_name") or "Customer",
            "billing_last_name": "",
            "billing_address": addr.get("address_line1", ""),
            "billing_address_2": addr.get("address_line2") or "",
            "billing_city": addr.get("city", ""),
            "billing_pincode": addr.get("postal_code", ""),
            "billing_state": addr.get("state", ""),
            "billing_country": addr.get("country") or "India",
            "billing_email": addr.get("email") or order_doc.get("user_email", ""),
            "billing_phone": addr.get("phone", ""),
            "shipping_is_billing": True,
            # `selling_price` is GST-INCLUSIVE (per Shiprocket's API docs) —
            # exactly how our storefront prices work. Passing `tax` (the
            # total GST %) and `hsn` is what makes Shiprocket's generated
            # invoice back-calculate the taxable value and show the
            # CGST/SGST (intra-state) or IGST (inter-state) split instead
            # of 0.00 | 0.00; without them the invoice legally shows no tax
            # collected at all. The intra/inter split itself is decided by
            # Shiprocket from pickup state vs place of supply — we only
            # supply the rate.
            "order_items": [
                {
                    "name": item.get("product_name", "Item"),
                    "sku": item.get("product_id", "SKU"),
                    "units": item.get("quantity", 1),
                    "selling_price": item.get("unit_price", 0),
                    **(
                        {
                            "tax": self._gst_rate_value(),
                            "hsn": settings.gst_hsn_code,
                        }
                        if settings.gst_enabled
                        else {}
                    ),
                }
                for item in order_doc.get("items", [])
            ],
            "payment_method": payment_method,
            "sub_total": order_doc.get("total_amount", 0),
            "length": length_cm,
            "breadth": breadth_cm,
            "height": height_cm,
            "weight": weight_kg,
        }

    async def get_courier_quotes(self, order_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not settings.shiprocket_pickup_pincode:
            raise ShiprocketAPIError("SHIPROCKET_PICKUP_PINCODE is not configured")
        weight_kg, _length, _breadth, _height = await self._order_package_dims(order_doc)
        delivery_pincode = order_doc.get("shipping_address", {}).get("postal_code", "")
        is_cod = order_doc.get("payment_method") == "cod"
        couriers = await self.client.check_serviceability(
            pickup_postcode=settings.shiprocket_pickup_pincode,
            delivery_postcode=delivery_pincode,
            weight=weight_kg,
            cod=is_cod,
        )
        quotes = [
            {
                "courier_company_id": c.get("courier_company_id"),
                "courier_name": c.get("courier_name"),
                "rate": c.get("rate"),
                "estimated_delivery_days": c.get("estimated_delivery_days"),
                "etd": c.get("etd"),
                "cod": c.get("cod"),
            }
            for c in couriers
        ]
        quotes.sort(key=lambda q: (q.get("rate") is None, q.get("rate") or 0))
        return quotes

    async def ship_order(self, order_id: str, courier_company_id: Optional[int] = None) -> Dict[str, Any]:
        """The "Ready to Ship" action — wrapped in a short-lived Redis lock so
        a double-click or a retry-after-500 can't race the "already shipped?"
        read (in _ship_order_impl below) against the Shiprocket API call and
        create two real shipments. This closes the *concurrent*-call window;
        _ship_order_impl's own field-presence checks are what make a
        *sequential* retry after a genuine partial failure safe — the two
        are complementary, not redundant.
        """
        redis = await redis_client.get_client()
        lock_key = f"shiprocket:ship_lock:{order_id}"
        # Long enough to cover create + AWB + label + invoice + pickup (each
        # its own ~20s Shiprocket call) without holding the lock indefinitely
        # if the process crashes mid-shipment.
        acquired = await redis.set(lock_key, "1", nx=True, ex=120)
        if not acquired:
            raise ShiprocketAPIError(
                "This order is already being shipped (another request is in "
                "progress) — wait a moment and check its shipment status "
                "before retrying."
            )
        try:
            return await self._ship_order_impl(order_id, courier_company_id)
        finally:
            await redis.delete(lock_key)

    async def _ship_order_impl(self, order_id: str, courier_company_id: Optional[int] = None) -> Dict[str, Any]:
        """The "Ready to Ship" action. Idempotent — safe to call again after a
        partial failure; already-completed steps are skipped.
        """
        collection = await self._collection()
        order_doc = await collection.find_one({"order_id": order_id})
        if not order_doc:
            raise ValueError("Order not found")

        if not order_doc.get("shiprocket_order_id"):
            weight_kg, length_cm, breadth_cm, height_cm = await self._order_package_dims(order_doc)
            payload = self._build_create_order_payload(order_doc, weight_kg, length_cm, breadth_cm, height_cm)
            result = await self.client.create_order(payload)
            sr_order_id = result.get("order_id")
            sr_shipment_id = result.get("shipment_id")
            if not sr_order_id or not sr_shipment_id:
                # Shiprocket can return 200 with an error body (e.g. wrong
                # pickup_location) rather than a 4xx — don't silently save
                # None ids and let a confusing failure surface downstream at
                # AWB assignment instead.
                if logger:
                    logger.error(f"Shiprocket create_order returned no ids for {order_id}: {result}")
                raise ShiprocketAPIError(
                    f"Shiprocket order creation did not return valid ids: {result.get('message') or result}"
                )
            await collection.update_one(
                {"order_id": order_id},
                {"$set": {"shiprocket_order_id": sr_order_id, "shiprocket_shipment_id": sr_shipment_id}},
            )
            order_doc["shiprocket_order_id"] = sr_order_id
            order_doc["shiprocket_shipment_id"] = sr_shipment_id
            logger.info(f"Shiprocket shipment created for order {order_id}: {sr_shipment_id}")

        shipment_id = order_doc["shiprocket_shipment_id"]

        if not order_doc.get("awb_code"):
            chosen_courier_id = courier_company_id
            if chosen_courier_id is None:
                quotes = await self.get_courier_quotes(order_doc)
                if not quotes:
                    raise ShiprocketAPIError("No couriers available for this order")
                if settings.shiprocket_default_courier_selection == "fastest":
                    quotes = sorted(
                        quotes,
                        key=lambda q: (
                            q.get("estimated_delivery_days") is None,
                            q.get("estimated_delivery_days") or "999",
                        ),
                    )
                chosen_courier_id = quotes[0]["courier_company_id"]

            awb_result = await self.client.assign_awb(shipment_id=shipment_id, courier_id=chosen_courier_id)
            awb_data = (awb_result.get("response") or {}).get("data") or {}
            awb_code = awb_data.get("awb_code")
            if not awb_code:
                # Shiprocket's docs show TWO distinct "not yet got an awb_code"
                # shapes: a hard failure (awb_assign_status=0 + error message,
                # e.g. low wallet balance) AND a legitimate async/queued
                # success ({"success": true, "message": "We are processing
                # your request"}) — these must not be treated the same way.
                # Misreading the second as a failure would falsely alarm the
                # admin over a shipment that's actually still being assigned.
                if awb_result.get("success") is True:
                    if logger:
                        logger.info(
                            f"Shiprocket AWB assignment queued (async) for {order_id}: {awb_result.get('message')}"
                        )
                    raise ShiprocketAPIError(
                        "Shiprocket is still processing the AWB assignment — retry 'Ready to Ship' in a minute.",
                        payload=awb_result,
                    )
                # Shiprocket can return 200 with awb_assign_status=0 and an
                # error message (e.g. low wallet balance) rather than a 4xx —
                # don't silently continue to label/invoice/pickup with no AWB.
                reason = (
                    awb_result.get("message")
                    or awb_data.get("awb_assign_error")
                    or awb_result
                )
                if logger:
                    logger.error(f"Shiprocket AWB assignment failed for {order_id}: {reason}")
                raise ShiprocketAPIError(f"Shiprocket AWB assignment failed: {reason}")
            courier_name = awb_data.get("courier_name")
            resolved_courier_id = awb_data.get("courier_company_id", chosen_courier_id)
            # Confirmed live against the real account's track_url response
            # (the docs show multiple inconsistent patterns across different
            # endpoints — this one is empirically what THIS account's
            # single-AWB track endpoint actually returns). Overwritten with
            # the authoritative track_url from track() the first time it's called.
            tracking_url = f"https://shiprocket.co/tracking/{awb_code}"

            await collection.update_one(
                {"order_id": order_id},
                {
                    "$set": {
                        "awb_code": awb_code,
                        "courier_name": courier_name,
                        "courier_company_id": resolved_courier_id,
                        "tracking_url": tracking_url,
                        "shipment_status": "awb_assigned",
                    }
                },
            )
            order_doc.update(
                {
                    "awb_code": awb_code,
                    "courier_name": courier_name,
                    "courier_company_id": resolved_courier_id,
                    "tracking_url": tracking_url,
                    "shipment_status": "awb_assigned",
                }
            )
            await self._append_status_history(order_id, "awb_assigned", "AWB Assigned")
            if logger:
                logger.info(
                    f"Shiprocket AWB assigned for {order_id}: awb={awb_code} courier={courier_name}"
                )

        if not order_doc.get("shipping_label_url"):
            try:
                label_result = await self.client.generate_label(shipment_id=shipment_id)
                label_url = label_result.get("label_url")
                if label_url:
                    await collection.update_one({"order_id": order_id}, {"$set": {"shipping_label_url": label_url}})
                    order_doc["shipping_label_url"] = label_url
                    if logger:
                        logger.info(f"Shiprocket label generated for {order_id}: {label_url}")
                elif logger:
                    # Shiprocket's documented failure shape here is 200 OK
                    # with label_created=0 — no exception, so without this it
                    # fails completely silently with zero trace in the logs.
                    logger.warning(
                        f"Shiprocket label generation returned no label_url for {order_id}: {label_result}"
                    )
            except ShiprocketAPIError as e:
                logger.warning(f"Shiprocket label generation failed for {order_id}: {e}")

        if not order_doc.get("shipping_invoice_url"):
            try:
                invoice_result = await self.client.generate_invoice(order_id=order_doc["shiprocket_order_id"])
                invoice_url = invoice_result.get("invoice_url")
                if invoice_url:
                    await collection.update_one(
                        {"order_id": order_id}, {"$set": {"shipping_invoice_url": invoice_url}}
                    )
                    order_doc["shipping_invoice_url"] = invoice_url
                    if logger:
                        logger.info(f"Shiprocket invoice generated for {order_id}: {invoice_url}")
            except ShiprocketAPIError as e:
                logger.warning(f"Shiprocket invoice generation failed for {order_id}: {e}")

        if order_doc.get("shipment_status") == "awb_assigned":
            try:
                await self.client.generate_pickup(shipment_id=shipment_id)
                await collection.update_one({"order_id": order_id}, {"$set": {"shipment_status": "pickup_scheduled"}})
                order_doc["shipment_status"] = "pickup_scheduled"
                await self._append_status_history(order_id, "pickup_scheduled", "Pickup scheduled")
                if logger:
                    logger.info(f"Shiprocket pickup scheduled for {order_id}")
            except ShiprocketAPIError as e:
                logger.warning(f"Shiprocket pickup scheduling failed for {order_id}: {e}")

        # AWB assignment (the essential part) succeeded even if label/invoice/
        # pickup soft-failed above — those can be retried individually later.
        await collection.update_one({"order_id": order_id}, {"$set": {"fulfillment_status": "shipped"}})
        await order_ledger.append_event(
            order_id, "fulfillment_changed", "admin", {"from": "packed", "to": "shipped"},
        )

        if publish_alert:
            await publish_alert(
                EVENT_SHIPMENT_UPDATE,
                {
                    "order_id": order_id,
                    "status": "awb_assigned",
                    "courier_name": order_doc.get("courier_name"),
                    "awb_code": order_doc.get("awb_code"),
                },
            )

        return {
            "shiprocket_order_id": order_doc.get("shiprocket_order_id"),
            "shiprocket_shipment_id": order_doc.get("shiprocket_shipment_id"),
            "awb_code": order_doc.get("awb_code"),
            "courier_name": order_doc.get("courier_name"),
            "tracking_url": order_doc.get("tracking_url"),
            "shipping_label_url": order_doc.get("shipping_label_url"),
            "shipping_invoice_url": order_doc.get("shipping_invoice_url"),
            "fulfillment_status": "shipped",
        }

    def _is_terminal_shipment_status(self, status: Optional[str]) -> bool:
        return status in ("cancelled", "delivered", "rto_delivered", "failed")

    async def cancel_shipment(self, order_id: str) -> Dict[str, Any]:
        collection = await self._collection()
        order_doc = await collection.find_one({"order_id": order_id})
        if not order_doc:
            raise ValueError("Order not found")

        current_status = order_doc.get("shipment_status")
        if self._is_terminal_shipment_status(current_status):
            # Idempotent no-op: repeat clicks (or a slow double-click) must
            # not re-call Shiprocket's API or push duplicate history entries.
            if logger:
                logger.info(f"Shiprocket cancel_shipment: order {order_id} already {current_status}, no-op")
            return {"success": True, "already": current_status}

        if order_doc.get("awb_code"):
            await self.client.cancel_shipment(awb_code=order_doc["awb_code"])
        elif order_doc.get("shiprocket_order_id"):
            await self.client.cancel_order(order_id=order_doc["shiprocket_order_id"])
        else:
            raise ValueError("Order has no Shiprocket shipment to cancel")

        await collection.update_one({"order_id": order_id}, {"$set": {"shipment_status": "cancelled"}})
        await self._append_status_history(order_id, "cancelled", "Cancelled by admin")
        if publish_alert:
            await publish_alert(
                EVENT_SHIPMENT_UPDATE,
                {"order_id": order_id, "status": "cancelled", "raw_status": "Cancelled by admin"},
            )
        return {"success": True}

    async def track(self, order_id: str) -> Dict[str, Any]:
        """Live-refresh from Shiprocket AND persist to our own DB — this is
        the manual fallback path for when webhooks don't arrive (e.g. a
        Cloudflare tunnel isn't reachable), so "Refresh Tracking" actually
        syncs shipment_status / history, not just a read-only display value.
        """
        collection = await self._collection()
        order_doc = await collection.find_one({"order_id": order_id})
        if not order_doc or not order_doc.get("awb_code"):
            raise ValueError("Order has no AWB assigned yet")
        result = await self.client.track_by_awb(awb_code=order_doc["awb_code"])
        tracking_data = result.get("tracking_data") or {}
        if logger:
            logger.info(f"Shiprocket track() for order {order_id} awb={order_doc['awb_code']}: {tracking_data}")

        real_track_url = tracking_data.get("track_url")
        if real_track_url and real_track_url != order_doc.get("tracking_url"):
            await collection.update_one({"order_id": order_id}, {"$set": {"tracking_url": real_track_url}})

        shipment_track = tracking_data.get("shipment_track") or []
        raw_status = (shipment_track[0].get("current_status") if shipment_track else None) or tracking_data.get(
            "track_status"
        )
        scans = tracking_data.get("shipment_track_activities") or []
        if raw_status:
            await self._apply_status_update(order_id, raw_status, scans=scans)
        elif scans:
            await self._record_scans(order_id, scans)

        return tracking_data

    def verify_webhook_token(self, provided_token: Optional[str]) -> bool:
        expected = settings.shiprocket_webhook_token
        if not expected or not provided_token:
            return False
        return hmac.compare_digest(provided_token, expected)

    async def handle_webhook(self, payload: Dict[str, Any]) -> None:
        # Per Shiprocket docs, `order_id` in the webhook body is OUR reference
        # order_id (string); `sr_order_id` is Shiprocket's own id — opposite
        # naming from the create-order response. `scans` (when present) is
        # the full granular courier activity log (date/activity/location),
        # resent cumulatively on every call — persisted separately from our
        # own status-machine history via _record_scans's de-dupe.
        our_order_id = payload.get("order_id")
        raw_status = payload.get("current_status") or payload.get("shipment_status") or ""
        scans = payload.get("scans") or []
        if not our_order_id:
            if logger:
                logger.warning("Shiprocket webhook missing order_id")
            return

        mapped_status = await self._apply_status_update(
            our_order_id,
            raw_status,
            scans=scans,
            awb=payload.get("awb"),
            courier_name=payload.get("courier_name"),
        )
        if mapped_status is None and logger:
            logger.warning(f"Shiprocket webhook for unknown order_id={our_order_id}")
