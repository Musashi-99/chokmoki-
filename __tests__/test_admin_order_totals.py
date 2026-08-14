from __future__ import annotations

import os
import sys
from types import SimpleNamespace

os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.order_service import OrderService


def test_admin_totals_ignore_client_total():
    items = [
        SimpleNamespace(total_price=1000),
        SimpleNamespace(total_price=500),
    ]
    subtotal, shipping, discount, total = OrderService._admin_order_totals(
        items, shipping=50, discount=20
    )
    assert subtotal == 1500
    assert shipping == 50
    assert discount == 20
    assert total == 1530


def test_admin_totals_never_go_negative():
    items = [SimpleNamespace(total_price=100)]
    subtotal, shipping, discount, total = OrderService._admin_order_totals(
        items, shipping=0, discount=999
    )
    assert subtotal == 100
    assert total == 0


def test_admin_totals_treat_missing_as_zero():
    items = [SimpleNamespace(total_price=250)]
    subtotal, shipping, discount, total = OrderService._admin_order_totals(items, None, None)
    assert subtotal == 250
    assert shipping == 0
    assert discount == 0
    assert total == 250


def test_customer_pricing_never_goes_negative():
    items = [SimpleNamespace(total_price=100)]
    pricing = OrderService._recalculate_pricing(None, items)
    assert pricing.total == 100
    assert pricing.discount == 0
    assert pricing.shipping == 0
