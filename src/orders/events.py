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


async def publish_order_event(event_type: str, payload: Dict[str, Any]) -> Optional[str]:
    """Publish an order-lifecycle event. Always on (unlike alerts, which are
    gated on TELEGRAM_ENABLED) — this is core order processing, not optional.
    """
    return await event_bus.publish(ORDERS_STREAM_KEY, event_type, payload)
