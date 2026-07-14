"""Durable, queryable operational log — for notable backend events that
should be inspectable from the admin panel later, distinct from per-request
application logs (which only live in the container's log file/volume and
aren't easy to search or retain deliberately).

Not a replacement for src.plugins.logger — this is for events an admin
should be able to look back on and ask "did this happen, and why" (fallback
paths triggered, detected inconsistencies, degraded-mode operation), not for
routine request tracing.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.database.connection import db

SYSTEM_LOGS_COLLECTION = "system_logs"
DEFAULT_RETENTION_DAYS = 30


class SystemLogService:
    async def _db(self):
        return await db.get_database()

    async def ensure_indexes(self) -> None:
        database = await self._db()
        logs = database[SYSTEM_LOGS_COLLECTION]
        await logs.create_index([("created_at", -1)])
        await logs.create_index([("component", 1), ("created_at", -1)])
        # TTL index: auto-expire after DEFAULT_RETENTION_DAYS so this
        # collection can't grow unbounded — these are operational logs, not
        # an audit trail that needs indefinite retention (order_events is).
        await logs.create_index(
            "created_at", expireAfterSeconds=DEFAULT_RETENTION_DAYS * 86400, name="created_at_ttl"
        )

    async def log(
        self,
        *,
        component: str,
        level: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Best-effort: a logging failure must never break the caller's
        actual work, so this swallows its own exceptions after trying to
        fall back to the plain file logger.
        """
        try:
            database = await self._db()
            await database[SYSTEM_LOGS_COLLECTION].insert_one(
                {
                    "component": component,
                    "level": level,
                    "message": message,
                    "context": context or {},
                    "created_at": datetime.utcnow(),
                }
            )
        except Exception:
            try:
                from src.plugins.logger import logger

                if logger:
                    logger.error(f"SystemLogService.log failed to persist: [{component}] {message}")
            except Exception:
                pass

        # Error-level operational events (breaker trips, DLQ drops, worker
        # crashes, orphaned payments) are worth an immediate page, not just a
        # row an admin might check later — reuses the existing Telegram
        # alert channel (src/alerts/) rather than a separate mechanism. The
        # sources of these calls already self-limit how often they fire
        # (e.g. the breaker only logs "tripped" once per open window), so
        # this doesn't need its own additional rate limiting on top.
        if level == "error":
            try:
                from src.alerts.events import EVENT_SYSTEM_ERROR, publish_alert

                await publish_alert(
                    EVENT_SYSTEM_ERROR,
                    {"component": component, "message": message, "context": context or {}},
                )
            except Exception:
                pass

    async def list_logs(
        self,
        *,
        component: Optional[str] = None,
        level: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        database = await self._db()
        query: Dict[str, Any] = {}
        if component:
            query["component"] = component
        if level:
            query["level"] = level
        cursor = database[SYSTEM_LOGS_COLLECTION].find(query).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)
