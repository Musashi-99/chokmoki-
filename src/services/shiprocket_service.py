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
from src.plugins.logger import logger
from src.services.product_service import ProductService
from src.shiprocket.client import ShiprocketAPIError, ShiprocketClient, ShiprocketNotConfiguredError

# Optional alerts import (matches the established pattern in order_service.py)
try:
    from src.alerts.events import EVENT_SHIPMENT_UPDATE, publish_alert
except ImportError:
    EVENT_SHIPMENT_UPDATE = "shipment.updated"
    publish_alert = None


# Shiprocket's granular current_status strings -> our smaller shipment_status
# enum. Matched case-insensitively; anything unrecognized is logged and left
# as "pending" rather than guessed at.
_STATUS_MAP = {
    "awb assigned": "awb_assigned",
    "pickup scheduled": "pickup_scheduled",
    "pickup generated": "pickup_scheduled",
    "manifest generated": "pickup_scheduled",
    "picked up": "picked_up",
    "shipped": "picked_up",
    "in transit": "in_transit",
    "reached at destination hub": "in_transit",
    "out for delivery": "out_for_delivery",
    "delivered": "delivered",
    "rto initiated": "rto_initiated",
    "rto delivered": "rto_delivered",
    "cancelled": "cancelled",
    "cancelled shipment": "cancelled",
    "lost": "failed",
    "damaged": "failed",
}


def _map_status(raw_status: str) -> str:
    mapped = _STATUS_MAP.get((raw_status or "").strip().lower())
    if mapped is None and logger:
        logger.warning(f"Shiprocket webhook: unrecognized status '{raw_status}', leaving as pending")
    return mapped or "pending"


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

    async def _order_weight_kg(self, order_doc: Dict[str, Any]) -> float:
        total_grams = 0.0
        has_any = False
        product_service = ProductService()
        for item in order_doc.get("items", []):
            product = await product_service.get_by_id(item.get("product_id", ""))
            if product and product.weight_grams:
                total_grams += product.weight_grams * item.get("quantity", 1)
                has_any = True
        if not has_any:
            return settings.shiprocket_default_weight_kg
        return round(max(total_grams / 1000.0, settings.shiprocket_default_weight_kg), 3)

    def _build_create_order_payload(self, order_doc: Dict[str, Any], weight_kg: float) -> Dict[str, Any]:
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
            "order_items": [
                {
                    "name": item.get("product_name", "Item"),
                    "sku": item.get("product_id", "SKU"),
                    "units": item.get("quantity", 1),
                    "selling_price": item.get("unit_price", 0),
                }
                for item in order_doc.get("items", [])
            ],
            "payment_method": payment_method,
            "sub_total": order_doc.get("total_amount", 0),
            "length": settings.shiprocket_default_length_cm,
            "breadth": settings.shiprocket_default_breadth_cm,
            "height": settings.shiprocket_default_height_cm,
            "weight": weight_kg,
        }

    async def get_courier_quotes(self, order_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not settings.shiprocket_pickup_pincode:
            raise ShiprocketAPIError("SHIPROCKET_PICKUP_PINCODE is not configured")
        weight_kg = await self._order_weight_kg(order_doc)
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
        """The "Ready to Ship" action. Idempotent — safe to call again after a
        partial failure; already-completed steps are skipped.
        """
        collection = await self._collection()
        order_doc = await collection.find_one({"order_id": order_id})
        if not order_doc:
            raise ValueError("Order not found")

        if not order_doc.get("shiprocket_order_id"):
            weight_kg = await self._order_weight_kg(order_doc)
            payload = self._build_create_order_payload(order_doc, weight_kg)
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
                }
            )
            await self._append_status_history(order_id, "awb_assigned", "AWB Assigned")

        if not order_doc.get("shipping_label_url"):
            try:
                label_result = await self.client.generate_label(shipment_id=shipment_id)
                label_url = label_result.get("label_url")
                if label_url:
                    await collection.update_one({"order_id": order_id}, {"$set": {"shipping_label_url": label_url}})
                    order_doc["shipping_label_url"] = label_url
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
            except ShiprocketAPIError as e:
                logger.warning(f"Shiprocket invoice generation failed for {order_id}: {e}")

        try:
            await self.client.generate_pickup(shipment_id=shipment_id)
            await collection.update_one({"order_id": order_id}, {"$set": {"shipment_status": "pickup_scheduled"}})
            order_doc["shipment_status"] = "pickup_scheduled"
            await self._append_status_history(order_id, "pickup_scheduled", "Pickup scheduled")
        except ShiprocketAPIError as e:
            logger.warning(f"Shiprocket pickup scheduling failed for {order_id}: {e}")

        # AWB assignment (the essential part) succeeded even if label/invoice/
        # pickup soft-failed above — those can be retried individually later.
        await collection.update_one({"order_id": order_id}, {"$set": {"fulfillment_status": "shipped"}})

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

    async def cancel_shipment(self, order_id: str) -> Dict[str, Any]:
        collection = await self._collection()
        order_doc = await collection.find_one({"order_id": order_id})
        if not order_doc:
            raise ValueError("Order not found")

        if order_doc.get("awb_code"):
            await self.client.cancel_shipment(awb_code=order_doc["awb_code"])
        elif order_doc.get("shiprocket_order_id"):
            await self.client.cancel_order(order_id=order_doc["shiprocket_order_id"])
        else:
            raise ValueError("Order has no Shiprocket shipment to cancel")

        await collection.update_one({"order_id": order_id}, {"$set": {"shipment_status": "cancelled"}})
        await self._append_status_history(order_id, "cancelled", "Cancelled by admin")
        return {"success": True}

    async def track(self, order_id: str) -> Dict[str, Any]:
        collection = await self._collection()
        order_doc = await collection.find_one({"order_id": order_id})
        if not order_doc or not order_doc.get("awb_code"):
            raise ValueError("Order has no AWB assigned yet")
        result = await self.client.track_by_awb(awb_code=order_doc["awb_code"])
        return result.get("tracking_data") or {}

    def verify_webhook_token(self, provided_token: Optional[str]) -> bool:
        expected = settings.shiprocket_webhook_token
        if not expected or not provided_token:
            return False
        return hmac.compare_digest(provided_token, expected)

    async def handle_webhook(self, payload: Dict[str, Any]) -> None:
        # Per Shiprocket docs, `order_id` in the webhook body is OUR reference
        # order_id (string); `sr_order_id` is Shiprocket's own id — opposite
        # naming from the create-order response.
        our_order_id = payload.get("order_id")
        raw_status = payload.get("current_status") or payload.get("shipment_status") or ""
        if not our_order_id:
            if logger:
                logger.warning("Shiprocket webhook missing order_id")
            return

        collection = await self._collection()
        order_doc = await collection.find_one({"order_id": our_order_id})
        if not order_doc:
            if logger:
                logger.warning(f"Shiprocket webhook for unknown order_id={our_order_id}")
            return

        mapped_status = _map_status(raw_status)
        await collection.update_one({"order_id": our_order_id}, {"$set": {"shipment_status": mapped_status}})
        await self._append_status_history(our_order_id, mapped_status, raw_status)

        if publish_alert:
            await publish_alert(
                EVENT_SHIPMENT_UPDATE,
                {
                    "order_id": our_order_id,
                    "status": mapped_status,
                    "raw_status": raw_status,
                    "awb_code": payload.get("awb"),
                    "courier_name": payload.get("courier_name"),
                },
            )
