from __future__ import annotations

import asyncio
import json
import socket
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import redis.asyncio as redis_asyncio

from src.config import settings
from src.plugins.logger import logger

BLOCK_MS = 5000
BATCH_SIZE = 10
CLAIM_IDLE_MS = 30_000
CLAIM_EVERY_N_LOOPS = 6
MAX_DELIVERY_ATTEMPTS = 5

EventHandler = Callable[[str, Dict[str, Any]], Awaitable[None]]


class StreamConsumer:
    """Generic Redis Streams consumer-group loop.

    Reusable transport primitive with zero domain knowledge — pass it a
    stream key, a consumer-group name, and a `handler(event_type, payload)`
    coroutine; it takes care of consumer-group creation, blocking reads,
    reclaiming entries left pending by a crashed/restarted consumer
    (XAUTOCLAIM), and capping retries via XPENDING's delivery count before
    dropping a permanently-failing entry. Runs as a long-lived asyncio task
    for the process lifetime (started/stopped via app lifespan) — this only
    works because the app runs as a persistent process (Docker/uvicorn), not
    on per-request serverless invocations.
    """

    def __init__(self, stream_key: str, group_name: str, handler: EventHandler) -> None:
        self._stream_key = stream_key
        self._group_name = group_name
        self._handler = handler
        self._consumer_name = f"{socket.gethostname()}-{id(self)}"
        self._loops_since_claim = 0
        self._redis: Optional[redis_asyncio.Redis] = None

    async def _get_redis(self) -> redis_asyncio.Redis:
        """A dedicated connection, deliberately NOT the shared app-wide pool.

        XREADGROUP with BLOCK holds a connection open for up to BLOCK_MS
        waiting for new entries — that's normal for a stream consumer, but
        it must never share a pool sized for short-lived request-serving
        calls (whose socket_timeout is much shorter than BLOCK_MS, causing
        spurious client-side timeouts) or compete with request traffic for
        a small number of connections.
        """
        if self._redis is None:
            self._redis = redis_asyncio.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=(BLOCK_MS / 1000) + 5,
                max_connections=1,
            )
        return self._redis

    async def _close_redis(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    async def _ensure_group(self, redis: Any) -> None:
        try:
            await redis.xgroup_create(self._stream_key, self._group_name, id="0", mkstream=True)
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def _claim_stale(self, redis: Any) -> List[Tuple[str, Dict[str, str]]]:
        try:
            _cursor, claimed, _deleted = await redis.xautoclaim(
                self._stream_key,
                self._group_name,
                self._consumer_name,
                min_idle_time=CLAIM_IDLE_MS,
                start_id="0",
                count=BATCH_SIZE,
            )
            return claimed
        except Exception as e:
            if logger:
                logger.warning(f"Stream consumer xautoclaim failed for '{self._stream_key}': {e}")
            return []

    async def _delivery_count(self, redis: Any, entry_id: str) -> int:
        try:
            pending = await redis.xpending_range(
                self._stream_key, self._group_name, min=entry_id, max=entry_id, count=1
            )
            return pending[0]["times_delivered"] if pending else 1
        except Exception:
            return 1

    async def _process(self, redis: Any, entry_id: str, fields: Dict[str, str]) -> None:
        event_type = fields.get("type", "")
        try:
            payload = json.loads(fields.get("payload", "{}"))
            await self._handler(event_type, payload)
            await redis.xack(self._stream_key, self._group_name, entry_id)
        except Exception as e:
            delivery_count = await self._delivery_count(redis, entry_id)
            if logger:
                logger.warning(
                    f"Stream handler failed for '{event_type}' (attempt {delivery_count}): {e}"
                )
            if delivery_count >= MAX_DELIVERY_ATTEMPTS:
                if logger:
                    logger.error(
                        f"Dropping event {entry_id} from '{self._stream_key}' after "
                        f"{delivery_count} failed attempts"
                    )
                await redis.xack(self._stream_key, self._group_name, entry_id)

    async def run(self) -> None:
        redis = await self._get_redis()
        await self._ensure_group(redis)
        if logger:
            logger.info(
                f"Stream consumer '{self._consumer_name}' started on '{self._stream_key}' "
                f"(group '{self._group_name}')"
            )

        try:
            while True:
                try:
                    self._loops_since_claim += 1
                    if self._loops_since_claim >= CLAIM_EVERY_N_LOOPS:
                        self._loops_since_claim = 0
                        for entry_id, fields in await self._claim_stale(redis):
                            await self._process(redis, entry_id, fields)

                    response = await redis.xreadgroup(
                        self._group_name,
                        self._consumer_name,
                        {self._stream_key: ">"},
                        count=BATCH_SIZE,
                        block=BLOCK_MS,
                    )
                    for _stream, entries in response or []:
                        for entry_id, fields in entries:
                            await self._process(redis, entry_id, fields)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if logger:
                        logger.error(f"Stream consumer loop error on '{self._stream_key}': {e}")
                    await asyncio.sleep(2)
        finally:
            await self._close_redis()
            if logger:
                logger.info(f"Stream consumer '{self._consumer_name}' stopped")
