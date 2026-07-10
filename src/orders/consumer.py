from __future__ import annotations

from typing import Any, Dict

from src.orders.events import EVENT_PAYMENT_CAPTURED, ORDERS_STREAM_KEY
from src.plugins.logger import logger
from src.streams.consumer import MAX_DELIVERY_ATTEMPTS, StreamConsumer

CONSUMER_GROUP = "orders"


class OrderEventConsumer:
    """Background task wiring: durable Redis Streams transport for
    money-critical order events. Runs in the separate `worker` process
    (src/worker.py), not the API process — decoupled so an API restart/crash
    can never drop an in-flight payment confirmation, and vice versa.
    """

    def __init__(self) -> None:
        self._stream_consumer = StreamConsumer(
            ORDERS_STREAM_KEY, CONSUMER_GROUP, handler=self._dispatch, on_failure=self._on_failure
        )

    async def _dispatch(self, event_type: str, payload: Dict[str, Any]) -> None:
        if event_type == EVENT_PAYMENT_CAPTURED:
            await self._handle_payment_captured(payload)
        elif logger:
            logger.warning(f"OrderEventConsumer: unrecognized event type '{event_type}'")

    async def _on_failure(
        self, event_type: str, payload: Dict[str, Any], delivery_count: int, error: Exception
    ) -> None:
        """Records every retry (and the final give-up) into the unified
        order_events ledger — so an admin looking at one order sees the full
        payment story, not just a log line only ops would ever check.
        """
        order_id = payload.get("order_id")
        if not order_id:
            return
        from src.services import order_ledger

        if delivery_count >= MAX_DELIVERY_ATTEMPTS:
            await order_ledger.append_event(
                order_id, "payment_processing_failed", "system",
                {"event_type": event_type, "attempts": delivery_count, "error": str(error)},
            )
        else:
            await order_ledger.append_event(
                order_id, "payment_processing_retry", "system",
                {
                    "event_type": event_type,
                    "attempt": delivery_count,
                    "max_attempts": MAX_DELIVERY_ATTEMPTS,
                    "error": str(error),
                },
            )

    async def _handle_payment_captured(self, payload: Dict[str, Any]) -> None:
        from src.services.order_service import OrderService

        order_id = payload.get("order_id")
        razorpay_order_id = payload.get("razorpay_order_id")
        razorpay_payment_id = payload.get("razorpay_payment_id")
        if not order_id or not razorpay_order_id or not razorpay_payment_id:
            if logger:
                logger.error(f"OrderEventConsumer: incomplete payment.captured payload: {payload}")
            return

        service = OrderService()
        _order, status = await service.complete_pending_order(
            order_id, razorpay_order_id, razorpay_payment_id
        )
        if status == "not_found" and logger:
            logger.warning(
                f"OrderEventConsumer: payment.captured for unknown/expired order {order_id}"
            )

    async def run(self) -> None:
        await self._stream_consumer.run()
