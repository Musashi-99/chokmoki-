"""GeoIP lookup — Adapter pattern.

`GeoIPProvider` is the interface the rest of the app depends on. The concrete
adapter below wraps the in-house `geoip-discovery` Go microservice
(GET /lookup?ip=<addr> -> {"ip": ..., "geo": {"country": {"iso_code": "AU", ...}}}).
Swapping to MaxMind/ipapi/another vendor later only means writing a new
adapter class — no caller of `GeoIPProvider.lookup()` changes.
"""

from __future__ import annotations

import ipaddress
import json
from typing import Any, Dict, Optional, Protocol

import httpx

from src.config import settings

CACHE_PREFIX = "chokmoki:geoip:"
# Short TTL for a failed lookup (service down, network blip) — long enough
# that an outage doesn't get hammered by every request retrying it, short
# enough that recovery shows up quickly once the service is back.
FAILURE_CACHE_TTL_SECONDS = 300

_SUPPORTED = None


def _is_private_or_local(ip: str) -> bool:
    """True for loopback/private/link-local addresses — localhost, Docker
    bridge networks, LAN IPs. These can never resolve to a real country, so
    skip the network round-trip to geoip-discovery entirely rather than
    calling it (and caching a meaningless "default") every time. This is
    also why country-based testing locally must go through the storefront's
    country selector (explicit selection), not GeoIP."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local


def supported_countries() -> set[str]:
    global _SUPPORTED
    if _SUPPORTED is None:
        _SUPPORTED = {
            c.strip().upper()
            for c in (settings.supported_market_countries or "").split(",")
            if c.strip()
        }
    return _SUPPORTED


def map_to_market(iso_country: Optional[str]) -> str:
    """Map a raw ISO-3166 alpha-2 code to our market bucket, defaulting unmapped ones."""
    if not iso_country:
        return "default"
    code = iso_country.strip().upper()
    return code if code in supported_countries() else "default"


class GeoIPResult:
    __slots__ = ("ip", "country", "raw_country", "raw")

    def __init__(self, ip: str, country: str, raw_country: Optional[str], raw: Optional[Dict[str, Any]]):
        self.ip = ip
        self.country = country          # mapped bucket: IN/AU/NZ/default
        self.raw_country = raw_country   # untouched ISO code from the provider, for audit evidence
        self.raw = raw                   # full provider response, for audit evidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ip": self.ip,
            "country": self.country,
            "raw_country": self.raw_country,
            "raw": self.raw,
        }


class GeoIPProvider(Protocol):
    async def lookup(self, ip: str) -> GeoIPResult: ...


class GeoIPDiscoveryAdapter:
    """Adapts the internal geoip-discovery Go service to `GeoIPProvider`."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        self._base_url = (base_url or settings.geoip_service_url or "").rstrip("/")
        self._timeout = timeout if timeout is not None else settings.geoip_lookup_timeout_seconds

    async def lookup(self, ip: str) -> GeoIPResult:
        if not ip or ip == "unknown" or _is_private_or_local(ip):
            return GeoIPResult(ip=ip or "unknown", country="default", raw_country=None, raw=None)

        cache_key = f"{CACHE_PREFIX}{ip}"
        from src.services.cache_service import cache

        cached = await cache.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return GeoIPResult(
                    ip=ip,
                    country=data.get("country", "default"),
                    raw_country=data.get("raw_country"),
                    raw=data.get("raw"),
                )
            except json.JSONDecodeError:
                pass

        if not self._base_url:
            # Service not configured for this environment — fail open to "default"
            # rather than blocking checkout on a missing dependency. Not worth
            # caching: this is a static config state, not a network call.
            return GeoIPResult(ip=ip, country="default", raw_country=None, raw=None)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/lookup", params={"ip": ip})
                resp.raise_for_status()
                payload = resp.json()
        except Exception:
            failure = GeoIPResult(ip=ip, country="default", raw_country=None, raw=None)
            await cache.set(
                cache_key, json.dumps(failure.to_dict(), default=str), FAILURE_CACHE_TTL_SECONDS
            )
            return failure

        raw_country = (
            (payload.get("geo") or {}).get("country", {}).get("iso_code")
            if isinstance(payload, dict)
            else None
        )
        result = GeoIPResult(
            ip=ip,
            country=map_to_market(raw_country),
            raw_country=raw_country,
            raw=payload if isinstance(payload, dict) else None,
        )
        await cache.set(
            cache_key, json.dumps(result.to_dict(), default=str), settings.geoip_cache_ttl_seconds
        )
        return result
