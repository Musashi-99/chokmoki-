from __future__ import annotations

from typing import Any, Dict

from src.alerts.chain import AlertEvent, AlertHandler
from src.alerts.channels import NotificationChannel
from src.alerts.events import EVENT_ADMIN_MUTATION, EVENT_ORDER_CREATED
from src.plugins.logger import logger

# Admin-mutation resources worth a "setting changed" alert. Deliberately
# excludes: "orders" (has its own richer alert via OrderCreatedHandler),
# "products" (routine catalog edits — too frequent to be alert-worthy),
# "upload" (not a setting), "fraud" (not requested yet — add its own
# handler link later if wanted).
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
    settings_handler = SettingsChangedHandler(channel)
    fallback_handler = FallbackHandler()

    order_handler.set_next(settings_handler).set_next(fallback_handler)
    return order_handler
