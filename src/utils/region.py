"""Shared "is this shipping address actually in India?" check — used
wherever a decision depends on the physical destination of a parcel
(shipping eligibility, GST document type), as opposed to `pricing_country_used`
which only decides which MarketPrice bucket to charge. Kept in one place so
order_service.py and invoice_service.py can't drift apart on what counts as
"India" (a stray "Bharat" or lowercase "in" from an old address book entry
shouldn't silently pass one check and fail the other).
"""

from __future__ import annotations

from typing import Optional

INDIA_ADDRESS_NAMES = {"india", "in", "bharat"}


def is_india_address(shipping_country: Optional[str]) -> bool:
    return (shipping_country or "").strip().lower() in INDIA_ADDRESS_NAMES
