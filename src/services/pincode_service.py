from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

PIN_RE = re.compile(r"^\d{6}$")
INDIA_POST_URL = "https://api.postalpincode.in/pincode/{pincode}"
CACHE_TTL_SECONDS = 60 * 60 * 24 * 30
CACHE_PREFIX = "chokmoki:pincode:"


def is_valid_pincode(pincode: str) -> bool:
    return bool(PIN_RE.fullmatch(pincode or ""))


def parse_india_post(payload: Any) -> Optional[dict[str, str]]:
    if not isinstance(payload, list) or not payload:
        return None
    entry = payload[0]
    if not isinstance(entry, dict) or str(entry.get("Status", "")).lower() != "success":
        return None
    offices = entry.get("PostOffice") or []
    if not isinstance(offices, list) or not offices:
        return None
    chosen = next(
        (o for o in offices if isinstance(o, dict) and o.get("DeliveryStatus") == "Delivery"),
        offices[0] if isinstance(offices[0], dict) else None,
    )
    if not isinstance(chosen, dict):
        return None
    city = str(chosen.get("District") or chosen.get("Block") or chosen.get("Name") or "").strip()
    state = str(chosen.get("State") or "").strip()
    country = str(chosen.get("Country") or "India").strip()
    locality = str(chosen.get("Name") or "").strip()
    if not city or not state:
        return None
    return {"city": city, "state": state, "country": country, "locality": locality}


class PincodeService:
    async def lookup(self, pincode: str) -> Optional[dict[str, str]]:
        if not is_valid_pincode(pincode):
            return None

        from src.services.cache_service import cache

        cache_key = f"{CACHE_PREFIX}{pincode}"
        if cache:
            cached = await cache.get(cache_key)
            if cached:
                try:
                    data = json.loads(cached)
                    if isinstance(data, dict) and data.get("city") and data.get("state"):
                        return data
                except json.JSONDecodeError:
                    pass

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(INDIA_POST_URL.format(pincode=pincode))
                resp.raise_for_status()
                place = parse_india_post(resp.json())
        except Exception:
            return None

        if place and cache:
            await cache.set(cache_key, json.dumps(place), CACHE_TTL_SECONDS)
        return place
