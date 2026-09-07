"""Courier fulfillment — Strategy pattern, one provider per market.

India ships end-to-end today via Shiprocket. Australia/New Zealand orders
are already accepted (multi-region pricing + COD-everywhere — see
order_service.py), but no courier is wired up for them yet: fulfillment
for those is manual until a provider is added here. Adding a real one
later is exactly one new class + one registry entry — every call site
(admin_orders.py) goes through get_courier_provider() and never imports
ShiprocketService directly, so nothing else has to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class CourierUnavailableError(Exception):
    """Raised when a market has no courier provider wired up yet. Same
    shape as ShiprocketAPIError (status_code + payload) so route handlers
    can catch both together and return one clear 400."""

    def __init__(self, country: str):
        self.status_code = 400
        self.payload = {"country": country}
        super().__init__(
            f"Courier fulfillment isn't set up for {country} yet — ship this order "
            "manually and update its status/tracking by hand until a courier is added."
        )


class CourierProvider(ABC):
    @abstractmethod
    async def get_courier_quotes(self, order_doc: Dict[str, Any]) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def ship_order(
        self, order_id: str, courier_company_id: Optional[int] = None
    ) -> Dict[str, Any]: ...

    @abstractmethod
    async def cancel_shipment(self, order_id: str) -> Dict[str, Any]: ...

    @abstractmethod
    async def track(self, order_id: str) -> Dict[str, Any]: ...


class ShiprocketCourierProvider(CourierProvider):
    """India — delegates to the existing ShiprocketService unchanged."""

    def __init__(self) -> None:
        from src.services.shiprocket_service import ShiprocketService

        self._service = ShiprocketService()

    async def get_courier_quotes(self, order_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        return await self._service.get_courier_quotes(order_doc)

    async def ship_order(
        self, order_id: str, courier_company_id: Optional[int] = None
    ) -> Dict[str, Any]:
        return await self._service.ship_order(order_id, courier_company_id=courier_company_id)

    async def cancel_shipment(self, order_id: str) -> Dict[str, Any]:
        return await self._service.cancel_shipment(order_id)

    async def track(self, order_id: str) -> Dict[str, Any]:
        return await self._service.track(order_id)


class UnavailableCourierProvider(CourierProvider):
    """AU/NZ/default today — every action fails clearly instead of silently
    misbehaving (e.g. Shiprocket's Indian-pincode serviceability check
    against an Australian postcode)."""

    def __init__(self, country: str) -> None:
        self._country = country

    async def get_courier_quotes(self, order_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        raise CourierUnavailableError(self._country)

    async def ship_order(
        self, order_id: str, courier_company_id: Optional[int] = None
    ) -> Dict[str, Any]:
        raise CourierUnavailableError(self._country)

    async def cancel_shipment(self, order_id: str) -> Dict[str, Any]:
        raise CourierUnavailableError(self._country)

    async def track(self, order_id: str) -> Dict[str, Any]:
        raise CourierUnavailableError(self._country)


# Registry — add "AU"/"NZ" here (plus a provider class) once a courier is
# wired up for that market. Everything else already routes through
# get_courier_provider() and needs no further changes.
_PROVIDERS: Dict[str, type[CourierProvider]] = {
    "IN": ShiprocketCourierProvider,
}


def get_courier_provider(country: Optional[str]) -> CourierProvider:
    code = (country or "IN").strip().upper()
    provider_cls = _PROVIDERS.get(code)
    if provider_cls is None:
        return UnavailableCourierProvider(code)
    return provider_cls()


def order_country(order_doc: Dict[str, Any]) -> str:
    """The region an order was actually placed/priced under. Orders from
    before multi-region existed (or created straight from the admin panel)
    have no region_audit at all — those are always India."""
    region_audit = order_doc.get("region_audit") or {}
    return (region_audit.get("pricing_country_used") or "IN").strip().upper()
