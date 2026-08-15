from __future__ import annotations

import os
import sys

os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.invoice_service import InvoiceService, gst_state_code
from src.utils.money import money


def test_gst_state_code_aliases():
    assert gst_state_code("West Bengal") == "19"
    assert gst_state_code("WB") == "19"
    assert gst_state_code("w.b.") == "19"


def test_intra_state_matches_wb_alias(monkeypatch):
    from src.services import invoice_service

    monkeypatch.setattr(invoice_service.settings, "invoice_seller_state", "West Bengal")
    monkeypatch.setattr(invoice_service.settings, "invoice_seller_state_code", "19")
    svc = InvoiceService()
    assert svc._is_intra_state({"shipping_address": {"state": "WB"}}) is True
    assert svc._is_intra_state({"shipping_address": {"state": "Maharashtra"}}) is False


def test_cgst_sgst_remainder_sums_to_tax(monkeypatch):
    from src.services import invoice_service

    monkeypatch.setattr(invoice_service.settings, "gst_enabled", True)
    monkeypatch.setattr(invoice_service.settings, "gst_cgst_percent", 1.5)
    monkeypatch.setattr(invoice_service.settings, "gst_sgst_percent", 1.5)
    monkeypatch.setattr(invoice_service.settings, "invoice_seller_state", "West Bengal")
    monkeypatch.setattr(invoice_service.settings, "invoice_seller_state_code", "19")
    svc = InvoiceService()
    rows = svc._tax_lines(
        {
            "shipping_address": {"state": "West Bengal"},
            "items": [{"product_name": "Ring", "product_id": "1", "quantity": 1, "unit_price": 1500}],
        },
        "tax_invoice",
    )
    row = rows[0]
    assert money(row["cgst"] + row["sgst"]) == money(row["total"] - row["taxable"])
    assert row["igst"] == 0.0
    assert row["total"] == row["net"]
    assert row["gross"] == 1500


def test_discounted_invoice_identity(monkeypatch):
    from src.services import invoice_service
    from src.utils.money import money

    monkeypatch.setattr(invoice_service.settings, "gst_enabled", True)
    monkeypatch.setattr(invoice_service.settings, "gst_cgst_percent", 1.5)
    monkeypatch.setattr(invoice_service.settings, "gst_sgst_percent", 1.5)
    monkeypatch.setattr(invoice_service.settings, "invoice_seller_state", "West Bengal")
    monkeypatch.setattr(invoice_service.settings, "invoice_seller_state_code", "19")
    svc = InvoiceService()
    order = {
        "shipping_address": {"state": "West Bengal"},
        "items": [
            {"product_name": "Ring", "product_id": "1", "quantity": 1, "unit_price": 1000},
        ],
        "discount": 100,
        "shipping": 50,
        "total_amount": 950,
        "applied_discount": {"type": "CART", "code": "SAVE100"},
    }
    rows = svc._tax_lines(order, "tax_invoice")
    totals = svc._commercial_totals(order, rows)
    assert totals["gross"] == 1000
    assert totals["discount"] == 100
    assert totals["net_goods"] == 900
    assert totals["shipping"] == 50
    assert money(totals["gross"] - totals["discount"] + totals["shipping"]) == totals["grand"]
    assert money(totals["net_goods"] + totals["shipping"]) == totals["grand"]
    assert money(totals["taxable"] + totals["cgst"] + totals["sgst"]) == totals["net_goods"]
    assert rows[0]["total"] == rows[0]["net"]
    assert rows[0]["gross"] == 1000


def test_product_coupon_gst_only_on_eligible_line(monkeypatch):
    from src.services import invoice_service

    monkeypatch.setattr(invoice_service.settings, "gst_enabled", True)
    monkeypatch.setattr(invoice_service.settings, "gst_cgst_percent", 1.5)
    monkeypatch.setattr(invoice_service.settings, "gst_sgst_percent", 1.5)
    monkeypatch.setattr(invoice_service.settings, "invoice_seller_state", "West Bengal")
    monkeypatch.setattr(invoice_service.settings, "invoice_seller_state_code", "19")
    svc = InvoiceService()
    order = {
        "shipping_address": {"state": "West Bengal"},
        "items": [
            {"product_name": "Ring", "product_id": "ring", "quantity": 1, "unit_price": 2000},
            {"product_name": "Chain", "product_id": "chain", "quantity": 1, "unit_price": 1000},
        ],
        "discount": 200,
        "shipping": 0,
        "total_amount": 2800,
        "applied_discount": {"type": "PRODUCT", "code": "RING10", "product_ids": ["ring"]},
    }
    rows = svc._tax_lines(order, "tax_invoice")
    totals = svc._commercial_totals(order, rows)
    assert rows[0]["discount"] == 200
    assert rows[1]["discount"] == 0
    assert rows[0]["net"] == 1800
    assert rows[1]["net"] == 1000
    assert totals["net_goods"] == 2800
    assert money(totals["taxable"] + totals["cgst"] + totals["sgst"]) == totals["net_goods"]
