"""Resolve a `MarketPrice` for a product + country — a second, simpler
Chain of Responsibility: exact-country match, then the "default" bucket.
Kept separate from `resolvers.py` (which decides *which country*) so each
chain stays small and single-purpose.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from src.models.product import MarketPrice


class PriceLookupHandler(ABC):
    def __init__(self, next_handler: Optional["PriceLookupHandler"] = None):
        self.next = next_handler

    @abstractmethod
    def resolve(self, prices: List[MarketPrice], country: str) -> Optional[MarketPrice]: ...

    def handle(self, prices: List[MarketPrice], country: str) -> Optional[MarketPrice]:
        result = self.resolve(prices, country)
        if result:
            return result
        if self.next:
            return self.next.handle(prices, country)
        return None


class ExactCountryMatchHandler(PriceLookupHandler):
    def resolve(self, prices: List[MarketPrice], country: str) -> Optional[MarketPrice]:
        for p in prices:
            if p.country == country:
                return p
        return None


class DefaultBucketHandler(PriceLookupHandler):
    def resolve(self, prices: List[MarketPrice], country: str) -> Optional[MarketPrice]:
        for p in prices:
            if p.country == "default":
                return p
        return None


def build_price_lookup_chain() -> PriceLookupHandler:
    return ExactCountryMatchHandler(next_handler=DefaultBucketHandler())


def resolve_price(prices: List[MarketPrice], country: str) -> MarketPrice:
    match = build_price_lookup_chain().handle(prices, country)
    if match is None:
        raise ValueError("Product has no 'default' price bucket configured")
    return match
