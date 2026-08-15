from __future__ import annotations

import os
import sys

os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal

from src.utils.money import allocate_shares, inr_to_paise, money, paise_to_inr


def test_money_half_up_paise():
    assert money(1.005) == 1.01
    assert money(10.126) == 10.13
    assert money(1499.995) == 1500.00
    assert money("19.99") == 19.99
    assert money(Decimal("0.1") + Decimal("0.2")) == 0.30


def test_inr_to_paise_matches_money():
    assert inr_to_paise(1.005) == 101
    assert inr_to_paise(10.126) == 1013
    assert inr_to_paise(1499.995) == 150000
    assert inr_to_paise(19.99) == 1999
    assert inr_to_paise(1500) == 150000


def test_paise_to_inr_round_trip():
    assert paise_to_inr(1999) == 19.99
    assert paise_to_inr(101) == 1.01
    assert inr_to_paise(paise_to_inr(1999)) == 1999


def test_allocate_shares_remainder_on_last_line():
    shares = allocate_shares([1000.0, 1000.0, 1000.0], 100)
    assert money(sum(shares)) == 100
    assert shares[-1] == money(100 - shares[0] - shares[1])


def test_allocate_shares_product_mask():
    shares = allocate_shares([2000.0, 3000.0], 200, [True, False])
    assert shares == [200.0, 0.0]
