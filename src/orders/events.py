"""Order-lifecycle event stream — reuses the generic Redis Streams transport
in src/streams/event_bus.py, same pattern as src/alerts/events.py.

Separate stream from the alerts stream (chokmoki:alerts:stream) — different
concern, different consumer group. This one exists specifically to make
Razorpay payment-webhook processing crash-safe: the webhook route verifies
the signature (must stay synchronous) then XADDs here and returns 200
immediately, instead of doing the whole Mongo write inline. If the process
crashes mid-processing, src/orders/consumer.py's StreamConsumer redelivers
the event on restart (XAUTOCLAIM) — safe because complete_pending_order()
is already idempotent (Mongo upsert on a unique order_id index).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.streams import event_bus

ORDERS_STREAM_KEY = "chokmoki:orders:events"

EVENT_PAYMENT_CAPTURED = "payment.captured"
# Shiprocket courier-update webhook payload — same durability rationale as
# EVENT_PAYMENT_CAPTURED above. Note: Shiprocket's own webhook delivery
# system requires a bare 200 response regardless of outcome (a non-200 is
# treated as a delivery failure on their end, not "please retry" — see
# api/routes/orders.py's shiprocket_webhook docstring), so this doesn't win
# a Shiprocket-side retry the way the Razorpay webhook implicitly can. What
# it does win: the actual Mongo writes (src/services/shiprocket_service.py's
# handle_webhook) move off the API's request-handling event loop and get
# our own retry/DLQ safety net (src/streams/consumer.py) instead of a single
# fire-and-forget try/except with no retry at all.
EVENT_SHIPMENT_UPDATE = "shipment.update"


async def publish_order_event(
    event_type: str, payload: Dict[str, Any], *, correlation_id: Optional[str] = None
) -> Optional[str]:
    """Publish an order-lifecycle event. Always on (unlike alerts, which are
    gated on TELEGRAM_ENABLED) — this is core order processing, not optional.
    """
    return await event_bus.publish(
        ORDERS_STREAM_KEY, event_type, payload, correlation_id=correlation_id
    )
