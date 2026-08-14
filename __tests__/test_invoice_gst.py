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
    assert round(row["cgst"] + row["sgst"], 2) == round(row["total"] - row["taxable"], 2)
    assert row["igst"] == 0.0
