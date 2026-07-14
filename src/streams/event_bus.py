from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.database.redis_connection import redis_client
from src.plugins.logger import logger

DEFAULT_MAXLEN = 5000


async def publish(
    stream_key: str,
    event_type: str,
    payload: Dict[str, Any],
    *,
    maxlen: int = DEFAULT_MAXLEN,
    correlation_id: Optional[str] = None,
) -> Optional[str]:
    """Push an event onto a Redis stream.

    Generic transport, no domain knowledge — callers (e.g. src/alerts/events.py)
    decide which stream and whether the feature is even enabled. A single XADD
    is a sub-millisecond round trip, so calling this from a request handler
    never meaningfully blocks the request; the actual processing happens later
    in a background consumer (src/streams/consumer.py), fully decoupled from
    this call. Never raises: a publish failure must not break the caller.

    correlation_id, if passed (from the originating request's
    CorrelationIdMiddleware), rides along in the event so a worker-side log
    line about processing this event can be tied back to the request that
    triggered it — otherwise the API and worker logs are two unconnected
    timelines for what's really one causal chain.
    """
    try:
        redis = await redis_client.get_client()
        fields: Dict[str, Any] = {
            "type": event_type,
            "payload": json.dumps(payload, default=str),
            "event_id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        if correlation_id:
            fields["correlation_id"] = correlation_id
        entry_id = await redis.xadd(
            stream_key,
            fields,
            maxlen=maxlen,
            approximate=True,
        )
        return entry_id
    except Exception as e:
        if logger:
            logger.warning(f"Failed to publish event '{event_type}' to stream '{stream_key}': {e}")
        return None
