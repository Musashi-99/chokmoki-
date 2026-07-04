from __future__ import annotations

from typing import Any, Dict, Optional

from src.config import settings
from src.streams import event_bus

ALERTS_STREAM_KEY = "chokmoki:alerts:stream"

EVENT_ORDER_CREATED = "order.created"
EVENT_ADMIN_MUTATION = "admin.mutation"


async def publish_alert(event_type: str, payload: Dict[str, Any]) -> Optional[str]:
    """Publish an alert-worthy event. No-ops (and never raises) if alerts
    aren't configured, so callers on a request's hot path never pay for
    Redis I/O when the feature is off.
    """
    if not settings.telegram_enabled:
        return None
    return await event_bus.publish(ALERTS_STREAM_KEY, event_type, payload)
