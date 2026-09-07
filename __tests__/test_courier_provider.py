"""Courier provider Strategy — see src/shipping/courier_provider.py."""
from unittest.mock import MagicMock, patch

import pytest

from src.shipping.courier_provider import (
    CourierUnavailableError,
    ShiprocketCourierProvider,
    UnavailableCourierProvider,
    get_courier_provider,
    order_country,
)


def test_india_resolves_to_shiprocket():
    # ShiprocketCourierProvider constructs a real ShiprocketService, which
    # requires SHIPROCKET_* config this test environment doesn't have —
    # stub it out; the point here is only which provider *class* IN
    # resolves to, not ShiprocketService's own config validation.
    with patch("src.services.shiprocket_service.ShiprocketService", return_value=MagicMock()):
        assert isinstance(get_courier_provider("IN"), ShiprocketCourierProvider)
        assert isinstance(get_courier_provider("in"), ShiprocketCourierProvider)


def test_missing_country_defaults_to_india():
    with patch("src.services.shiprocket_service.ShiprocketService", return_value=MagicMock()):
        assert isinstance(get_courier_provider(None), ShiprocketCourierProvider)


@pytest.mark.parametrize("country", ["AU", "NZ", "default", "US"])
def test_unwired_markets_get_unavailable_provider(country):
    provider = get_courier_provider(country)
    assert isinstance(provider, UnavailableCourierProvider)


@pytest.mark.asyncio
async def test_unavailable_provider_raises_clearly_on_every_action():
    provider = get_courier_provider("AU")
    for coro in (
        provider.get_courier_quotes({}),
        provider.ship_order("ord-1"),
        provider.cancel_shipment("ord-1"),
        provider.track("ord-1"),
    ):
        with pytest.raises(CourierUnavailableError, match="AU"):
            await coro


def test_order_country_reads_pricing_country_used():
    assert order_country({"region_audit": {"pricing_country_used": "AU"}}) == "AU"
    assert order_country({"region_audit": {"pricing_country_used": "au"}}) == "AU"


def test_order_country_defaults_to_india_when_no_region_audit():
    # Orders from before multi-region existed, or created from the admin
    # panel, never carry a region_audit at all.
    assert order_country({}) == "IN"
    assert order_country({"region_audit": None}) == "IN"
