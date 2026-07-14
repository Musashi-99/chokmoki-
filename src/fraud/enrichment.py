"""Fraud signal enrichment: velocity, duplicates, device, network."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Optional

from src.config import settings
from src.database.redis_connection import redis_client
from src.fraud.models import FraudContext

DISPOSABLE_EMAIL_PATTERN = re.compile(
    r"@("
    r"mailinator|tempmail|10minutemail|guerrillamail|yopmail|"
    r"throwaway|trashmail|dispostable|maildrop|getnada"
    r")\.",
    re.IGNORECASE,
)

TOR_EXIT_CIDRS = (
    "185.220.100.0/22",
    "185.220.101.0/24",
    "192.42.116.0/22",
    "45.83.140.0/22",
)


class FraudEnrichmentService:
    async def enrich(
        self, *, ctx: FraudContext, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        email = (
            ctx.email
            or payload.get("userEmail")
            or payload.get("user_email")
            or ""
        ).strip().lower()
        device_id = (
            ctx.device_id
            or payload.get("deviceId")
            or payload.get("device_id")
            or (ctx.attributes or {}).get("device_id")
        )
        velocity = await self._velocity_counters(ctx=ctx, email=email, device_id=device_id)
        duplicate_order = await self._duplicate_order_flag(
            email=email, payload=payload, event_type=ctx.event_type
        )
        return {
            "velocity": velocity,
            "attributes": {
                "disposable_email": self._is_disposable_email(email),
                "tor_exit": self._is_tor_exit(ctx.ip),
                "vpn_proxy_hint": self._vpn_proxy_hint(ctx),
                "device_id": device_id,
                "duplicate_order": duplicate_order,
            },
        }

    @staticmethod
    def _is_disposable_email(email: str) -> bool:
        return bool(email and DISPOSABLE_EMAIL_PATTERN.search(email))

    @staticmethod
    def _is_tor_exit(ip: Optional[str]) -> bool:
        if not ip:
            return False
        try:
            import ipaddress

            addr = ipaddress.ip_address(ip)
            for cidr in TOR_EXIT_CIDRS:
                if addr in ipaddress.ip_network(cidr, strict=False):
                    return True
        except ValueError:
            return False
        return False

    @staticmethod
    def _vpn_proxy_hint(ctx: FraudContext) -> bool:
        attrs = ctx.attributes or {}
        return bool(attrs.get("vpn_proxy_hint") or attrs.get("proxy_detected"))

    async def _velocity_counters(
        self,
        *,
        ctx: FraudContext,
        email: str,
        device_id: Optional[str],
    ) -> Dict[str, int]:
        if not settings.fraud_enabled:
            return {
                "email_orders_1h": 0,
                "ip_orders_1h": 0,
                "device_orders_1h": 0,
            }

        window = settings.fraud_velocity_window_seconds
        redis = await redis_client.get_client()
        counters = {
            "email_orders_1h": 0,
            "ip_orders_1h": 0,
            "device_orders_1h": 0,
        }
        if email:
            key = f"fraud:velocity:email:{email}"
            counters["email_orders_1h"] = int(await redis.incr(key))
            await redis.expire(key, window)
        if ctx.ip:
            key = f"fraud:velocity:ip:{ctx.ip}"
            counters["ip_orders_1h"] = int(await redis.incr(key))
            await redis.expire(key, window)
        if device_id:
            key = f"fraud:velocity:device:{device_id}"
            counters["device_orders_1h"] = int(await redis.incr(key))
            await redis.expire(key, window)
        return counters

    async def _duplicate_order_flag(
        self, *, email: str, payload: Dict[str, Any], event_type: str
    ) -> bool:
        """Read-only check: has this exact cart (email+items) already
        resulted in a REAL, successful order recently? Must NOT write here —
        this runs on every attempt, including ones that fail/get abandoned
        (a declined card, a closed Razorpay modal, switching payment method).
        Marking on every attempt (the previous bug) meant a customer whose
        first payment attempt didn't go through was hard-blocked from ever
        completing that same cart, by ANY payment method, for the whole
        dedup window — a real lost sale, not fraud. See mark_order_completed().
        """
        if event_type not in {"order_create", "order_initiate"}:
            return False
        fingerprint = self._order_fingerprint(email=email, payload=payload)
        if not fingerprint:
            return False

        redis = await redis_client.get_client()
        key = f"fraud:dup_order:{fingerprint}"
        return bool(await redis.exists(key))

    @classmethod
    async def mark_order_completed(cls, *, email: str, payload: Dict[str, Any]) -> None:
        """Call ONLY after an order actually, successfully completes (COD
        placed, or Razorpay payment captured) — this is what makes a
        genuinely repeated purchase attempt show up as a duplicate next time,
        without penalizing a legitimate retry of a failed/abandoned one.
        """
        fingerprint = cls._order_fingerprint(email=email, payload=payload)
        if not fingerprint:
            return
        redis = await redis_client.get_client()
        key = f"fraud:dup_order:{fingerprint}"
        await redis.set(key, "1", ex=settings.fraud_duplicate_window_seconds)

    @staticmethod
    def _order_fingerprint(*, email: str, payload: Dict[str, Any]) -> str:
        items = payload.get("items") or []
        normalized = {
            "email": email,
            "items": sorted(
                [
                    {
                        "productId": str(item.get("productId") or item.get("product_id")),
                        "quantity": int(item.get("quantity") or 0),
                        "variant": item.get("variant") or {},
                    }
                    for item in items
                ],
                key=lambda row: json.dumps(row, sort_keys=True),
            ),
        }
        raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
