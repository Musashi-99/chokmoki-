from __future__ import annotations

from typing import Any, Dict

from src.alerts.chain import AlertEvent, AlertHandler
from src.alerts.channels import NotificationChannel
from src.alerts.events import (
    EVENT_ADMIN_MUTATION,
    EVENT_CONTACT_SUBMITTED,
    EVENT_NEWSLETTER_SUBSCRIBED,
    EVENT_ORDER_CREATED,
    EVENT_PRODUCT_PRICE_CHANGED,
    EVENT_SHIPMENT_UPDATE,
)
from src.plugins.logger import logger

# Admin-mutation resources worth a "setting changed" alert. Deliberately
# excludes: "orders" (has its own richer alert via OrderCreatedHandler),
# "products" (routine catalog edits are too frequent to be alert-worthy,
# but a price change specifically gets its own richer alert via
# PriceChangedHandler), "upload" (not a setting), "fraud" (not requested
# yet — add its own handler link later if wanted).
SETTINGS_RESOURCES = {
    "hero",
    "navigation",
    "home-page",
    "shop-page",
    "policies",
    "studio-settings",
    "contact-page",
    "history-page",
    "product-page",
    "site-assets",
    "faq",
    "collection-slides",
    "testimonials",
    "categories",
    "blog-posts",
    "journal",
    "inbox",
}


def _format_order_alert(payload: Dict[str, Any]) -> str:
    order_id = payload.get("order_id", "unknown")
    total = payload.get("total_amount", 0)
    total_label = f"₹{total:,.0f}" if isinstance(total, (int, float)) else f"₹{total}"
    customer = payload.get("customer_name") or payload.get("user_email", "")
    payment_method = (payload.get("payment_method") or "").upper()

    lines = [
        "🎉 *New Order Received*",
        f"Order: `{order_id}`",
        f"Customer: {customer}",
        f"Total: {total_label}",
    ]
    if payment_method:
        lines.append(f"Payment: {payment_method}")

    items = payload.get("items", [])
    if items:
        lines.append("")
        lines.append("Items:")
        for item in items[:10]:
            name = item.get("product_name", "item")
            qty = item.get("quantity", 1)
            lines.append(f"• {name} × {qty}")

    return "\n".join(lines)


def _format_settings_alert(payload: Dict[str, Any]) -> str:
    actor = payload.get("actor_email", "unknown admin")
    resource = payload.get("resource", "unknown")
    method = payload.get("method", "")
    path = payload.get("path", "")
    return f"⚙️ *Setting Updated*\n{actor} updated `{resource}`\n{method} {path}"


def _format_price_label(value: Any) -> str:
    return f"₹{value:,.0f}" if isinstance(value, (int, float)) else f"₹{value}"


def _format_price_changed_alert(payload: Dict[str, Any]) -> str:
    name = payload.get("product_name", "product")
    old_price = _format_price_label(payload.get("old_price"))
    new_price = _format_price_label(payload.get("new_price"))
    actor = payload.get("actor_email")
    lines = [
        "💰 *Price Changed*",
        name,
        f"{old_price} → {new_price}",
    ]
    if actor:
        lines.append(f"By: {actor}")
    return "\n".join(lines)


def _format_contact_alert(payload: Dict[str, Any]) -> str:
    name = payload.get("name") or "Someone"
    email = payload.get("email", "")
    message = (payload.get("message") or payload.get("note") or "").strip()
    lines = [
        "📩 *New Contact Submission*",
        f"{name} ({email})" if email else name,
    ]
    if message:
        lines.append("")
        lines.append(message[:500])
    return "\n".join(lines)


def _format_newsletter_alert(payload: Dict[str, Any]) -> str:
    email = payload.get("email", "unknown")
    source = payload.get("source", "")
    lines = ["📰 *New Newsletter Signup*", email]
    if source:
        lines.append(f"Source: {source}")
    return "\n".join(lines)


def _format_shipment_alert(payload: Dict[str, Any]) -> str:
    order_id = payload.get("order_id", "unknown")
    status = (payload.get("status") or "unknown").replace("_", " ").title()
    lines = [
        "📦 *Shipment Update*",
        f"Order: `{order_id}`",
        f"Status: {status}",
    ]
    if payload.get("courier_name"):
        lines.append(f"Courier: {payload['courier_name']}")
    if payload.get("awb_code"):
        lines.append(f"AWB: {payload['awb_code']}")
    return "\n".join(lines)


class OrderCreatedHandler(AlertHandler):
    def __init__(self, channel: NotificationChannel) -> None:
        super().__init__()
        self._channel = channel

    async def _can_handle(self, event: AlertEvent) -> bool:
        return event.type == EVENT_ORDER_CREATED

    async def _process(self, event: AlertEvent) -> bool:
        sent = await self._channel.send(_format_order_alert(event.payload))
        if not sent:
            raise RuntimeError("Order alert channel send failed")
        return True


class SettingsChangedHandler(AlertHandler):
    def __init__(self, channel: NotificationChannel) -> None:
        super().__init__()
        self._channel = channel

    async def _can_handle(self, event: AlertEvent) -> bool:
        return event.type == EVENT_ADMIN_MUTATION and event.payload.get("resource") in SETTINGS_RESOURCES

    async def _process(self, event: AlertEvent) -> bool:
        sent = await self._channel.send(_format_settings_alert(event.payload))
        if not sent:
            raise RuntimeError("Settings alert channel send failed")
        return True


class PriceChangedHandler(AlertHandler):
    def __init__(self, channel: NotificationChannel) -> None:
        super().__init__()
        self._channel = channel

    async def _can_handle(self, event: AlertEvent) -> bool:
        return event.type == EVENT_PRODUCT_PRICE_CHANGED

    async def _process(self, event: AlertEvent) -> bool:
        sent = await self._channel.send(_format_price_changed_alert(event.payload))
        if not sent:
            raise RuntimeError("Price-change alert channel send failed")
        return True


class ContactSubmittedHandler(AlertHandler):
    def __init__(self, channel: NotificationChannel) -> None:
        super().__init__()
        self._channel = channel

    async def _can_handle(self, event: AlertEvent) -> bool:
        return event.type == EVENT_CONTACT_SUBMITTED

    async def _process(self, event: AlertEvent) -> bool:
        sent = await self._channel.send(_format_contact_alert(event.payload))
        if not sent:
            raise RuntimeError("Contact alert channel send failed")
        return True


class NewsletterSubscribedHandler(AlertHandler):
    def __init__(self, channel: NotificationChannel) -> None:
        super().__init__()
        self._channel = channel

    async def _can_handle(self, event: AlertEvent) -> bool:
        return event.type == EVENT_NEWSLETTER_SUBSCRIBED

    async def _process(self, event: AlertEvent) -> bool:
        sent = await self._channel.send(_format_newsletter_alert(event.payload))
        if not sent:
            raise RuntimeError("Newsletter alert channel send failed")
        return True


class ShipmentUpdateHandler(AlertHandler):
    def __init__(self, channel: NotificationChannel) -> None:
        super().__init__()
        self._channel = channel

    async def _can_handle(self, event: AlertEvent) -> bool:
        return event.type == EVENT_SHIPMENT_UPDATE

    async def _process(self, event: AlertEvent) -> bool:
        sent = await self._channel.send(_format_shipment_alert(event.payload))
        if not sent:
            raise RuntimeError("Shipment alert channel send failed")
        return True


class FallbackHandler(AlertHandler):
    """End of the chain — always matches. Logs and drops anything nobody
    else claimed (unknown event types, or admin mutations on resources
    intentionally excluded from SETTINGS_RESOURCES) so nothing is ever lost
    or crashes the consumer.
    """

    async def _can_handle(self, event: AlertEvent) -> bool:
        return True

    async def _process(self, event: AlertEvent) -> bool:
        if logger:
            logger.info(f"Alert event '{event.type}' had no interested handler; dropped")
        return True


def build_chain(channel: NotificationChannel) -> AlertHandler:
    order_handler = OrderCreatedHandler(channel)
    price_handler = PriceChangedHandler(channel)
    contact_handler = ContactSubmittedHandler(channel)
    newsletter_handler = NewsletterSubscribedHandler(channel)
    shipment_handler = ShipmentUpdateHandler(channel)
    settings_handler = SettingsChangedHandler(channel)
    fallback_handler = FallbackHandler()

    (
        order_handler.set_next(price_handler)
        .set_next(contact_handler)
        .set_next(newsletter_handler)
        .set_next(shipment_handler)
        .set_next(settings_handler)
        .set_next(fallback_handler)
    )
    return order_handler
