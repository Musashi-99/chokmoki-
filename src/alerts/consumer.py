from __future__ import annotations

from typing import Any, Dict

from src.alerts.chain import AlertEvent
from src.alerts.channels import TelegramChannel
from src.alerts.events import ALERTS_STREAM_KEY
from src.alerts.handlers import build_chain
from src.streams.consumer import StreamConsumer

CONSUMER_GROUP = "alerts"


class AlertConsumer:
    """Background task wiring: Chain of Responsibility handlers + Redis
    Streams transport. Started/stopped from api's lifespan (only valid
    because the app runs as a persistent Docker/uvicorn process).
    """

    def __init__(self) -> None:
        self._chain = build_chain(TelegramChannel())
        self._stream_consumer = StreamConsumer(
            ALERTS_STREAM_KEY, CONSUMER_GROUP, handler=self._dispatch
        )

    async def _dispatch(self, event_type: str, payload: Dict[str, Any]) -> None:
        await self._chain.handle(AlertEvent(type=event_type, payload=payload))

    async def run(self) -> None:
        await self._stream_consumer.run()
