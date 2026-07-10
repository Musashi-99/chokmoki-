"""Standalone worker process: runs the background stream consumers
(Telegram alerts + crash-safe Razorpay payment confirmation) in a SEPARATE
OS process/container from the API — not as asyncio tasks inside the request-
serving FastAPI process.

Why: those consumers used to run inside api/index.py's lifespan. A crash,
restart, or resource spike in the request-serving process took payment
processing down with it, and a stuck consumer competed with the API for the
same process's CPU/memory. This process shares the same Redis (transport)
and MongoDB (state) as the API — nothing else changes; XADD from the API,
XREADGROUP from here, exactly what Redis Streams is designed for.

Run via: python -m src.worker
"""
from __future__ import annotations

import asyncio
import signal
import sys

from dotenv import load_dotenv

load_dotenv(override=False)

from src.config import settings
from src.database.connection import db
from src.database.redis_connection import redis_client
from src.plugins.logger import logger
from src.alerts.consumer import AlertConsumer
from src.orders.consumer import OrderEventConsumer


async def main() -> None:
    await db.connect()
    await redis_client.connect()

    tasks: list[asyncio.Task] = []
    if settings.telegram_enabled:
        tasks.append(asyncio.create_task(AlertConsumer().run(), name="alert_consumer"))
    else:
        if logger:
            logger.info("Worker: Telegram alerts disabled (TELEGRAM_ENABLED=false), skipping AlertConsumer")

    # Unconditional — core payment processing, not an optional notification.
    tasks.append(asyncio.create_task(OrderEventConsumer().run(), name="order_event_consumer"))

    if logger:
        logger.info(f"Worker started with {len(tasks)} consumer task(s)")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()

    if logger:
        logger.info("Worker shutting down...")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    await db.close()
    await redis_client.close()
    if logger:
        logger.info("Worker shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
