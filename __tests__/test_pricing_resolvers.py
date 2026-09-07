"""Country resolution chain — see src/pricing/resolvers.py."""
from src.pricing.resolvers import resolve_country


def test_explicit_supported_country_wins():
    assert resolve_country(selected_country="AU", ip_country="IN") == "AU"


def test_row_forces_default_even_when_geoip_finds_a_supported_market():
    # A customer who deliberately picks "Rest of the World" must always get
    # the USD default bucket — never routed to a supported market just
    # because GeoIP happens to place them in one.
    assert resolve_country(selected_country="ROW", ip_country="IN") == "default"
    assert resolve_country(selected_country="row", ip_country=None) == "default"


def test_unsupported_selection_falls_through_to_geoip():
    assert resolve_country(selected_country="ZZ", ip_country="NZ") == "NZ"


def test_no_selection_or_geoip_falls_back_to_default():
    assert resolve_country(selected_country=None, ip_country=None) == "default"
    assert resolve_country(selected_country="", ip_country="") == "default"
