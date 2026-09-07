"""Country resolution — Chain of Responsibility.

Priority order: explicit user selection wins, then the IP-derived (GeoIP)
country, then the literal "default" bucket as a terminal fallback. Each
handler only decides "do I have an answer", never *how* a price is looked
up for that country — that is `price_lookup.py`'s job.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from src.pricing.geo_provider import supported_countries


@dataclass
class PricingContext:
    selected_country: Optional[str] = None   # explicit choice from the storefront (header/state)
    ip_country: Optional[str] = None         # resolved via GeoIPProvider for this request


class CountryResolutionHandler(ABC):
    def __init__(self, next_handler: Optional["CountryResolutionHandler"] = None):
        self.next = next_handler

    @abstractmethod
    def resolve(self, ctx: PricingContext) -> Optional[str]:
        """Return a country code if this handler can decide, else None to pass along."""

    def handle(self, ctx: PricingContext) -> str:
        result = self.resolve(ctx)
        if result:
            return result
        if self.next:
            return self.next.handle(ctx)
        return "default"


class UserSelectedCountryHandler(CountryResolutionHandler):
    def resolve(self, ctx: PricingContext) -> Optional[str]:
        code = (ctx.selected_country or "").strip().upper()
        # "ROW" ("Rest of the World") is an explicit customer choice, not a
        # market we price for — it must terminally resolve to the "default"
        # (USD) bucket, never fall through to GeoIP, or picking it would be
        # pointless for anyone GeoIP happens to place in a supported market.
        if code == "ROW":
            return "default"
        if code and code in supported_countries():
            return code
        return None


class GeoIPCountryHandler(CountryResolutionHandler):
    def resolve(self, ctx: PricingContext) -> Optional[str]:
        code = (ctx.ip_country or "").strip().upper()
        if code and code in supported_countries():
            return code
        return None


def build_default_chain() -> CountryResolutionHandler:
    """The chain used everywhere in the app: selected > geoip > default."""
    return UserSelectedCountryHandler(next_handler=GeoIPCountryHandler())


def resolve_country(selected_country: Optional[str], ip_country: Optional[str]) -> str:
    ctx = PricingContext(selected_country=selected_country, ip_country=ip_country)
    return build_default_chain().handle(ctx)
