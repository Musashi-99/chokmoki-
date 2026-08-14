from __future__ import annotations

import os
import sys

os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.shiprocket_service import ShiprocketService


def test_sub_total_is_item_sum_not_order_total():
    svc = object.__new__(ShiprocketService)
    payload = ShiprocketService._build_create_order_payload(
        svc,
        {
            "order_id": "ord-1",
            "payment_method": "cod",
            "user_email": "a@b.com",
            "shipping": 50,
            "discount": 20,
            "total_amount": 1530,
            "shipping_address": {
                "full_name": "A",
                "phone": "1",
                "address_line1": "x",
                "city": "Kolkata",
                "state": "West Bengal",
                "postal_code": "700016",
                "country": "India",
            },
            "items": [
                {"product_name": "Ring", "product_id": "p1", "quantity": 1, "unit_price": 1000},
                {"product_name": "Chain", "product_id": "p2", "quantity": 1, "unit_price": 500},
            ],
        },
        0.1,
        10,
        10,
        10,
    )
    assert payload["sub_total"] == 1500
    assert payload["shipping_charges"] == 50
    assert payload["total_discount"] == 20
