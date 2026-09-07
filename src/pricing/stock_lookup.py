"""Resolve a `MarketStock` for a product + country — same shape as
price_lookup.py: exact-country match, then the "default" bucket. Kept
separate so pricing and inventory stay independently testable even though
they share the same country-resolution chain (resolvers.py).
"""

from __future__ import annotations

from typing import List, Optional

from src.models.product import MarketStock


def resolve_stock(stock: List[MarketStock], country: str) -> Optional[MarketStock]:
    """Returns None when the product has no stock entries at all — i.e. it
    doesn't track inventory anywhere, always purchasable (same semantics
    the old single stock_qty=None had). Otherwise returns the exact-country
    row, falling back to "default" per the same rule MarketPrice uses."""
    if not stock:
        return None
    for s in stock:
        if s.country == country:
            return s
    for s in stock:
        if s.country == "default":
            return s
    return None
