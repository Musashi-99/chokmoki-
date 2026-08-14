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
from src.services.razorpay_service import inr_to_paise


def test_checkout_total_is_sum_of_catalog_line_totals():
    items = [
        SimpleNamespace(total_price=2499.0),
        SimpleNamespace(total_price=2499.0),
    ]
    pricing = OrderService._recalculate_pricing(None, items)
    assert pricing.subtotal == 4998.0
    assert pricing.discount == 0.0
    assert pricing.shipping == 0.0
    assert pricing.total == 4998.0
    assert inr_to_paise(pricing.total) == 499800
