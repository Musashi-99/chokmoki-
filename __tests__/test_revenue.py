from __future__ import annotations

import os
import sys

os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.revenue import revenue_mongo_match


def _matches(doc: dict) -> bool:
    q = revenue_mongo_match()
    if doc.get("payment_status") != q["payment_status"]:
        return False
    if doc.get("status", {}).get("type") in q["status.type"]["$nin"]:
        return False
    if doc.get("shipment_status") in q["shipment_status"]["$nin"]:
        return False
    if doc.get("custom_status") in q["custom_status"]["$nin"]:
        return False
    return True


def test_paid_accepted_counts():
    assert _matches(
        {
            "payment_status": "completed",
            "status": {"type": "accepted"},
            "shipment_status": "pending",
        }
    )


def test_unpaid_does_not_count():
    assert not _matches({"payment_status": "pending", "status": {"type": "accepted"}})


def test_shiprocket_cancel_does_not_count():
    assert not _matches(
        {
            "payment_status": "completed",
            "status": {"type": "accepted"},
            "shipment_status": "cancelled",
        }
    )


def test_custom_refund_does_not_count():
    assert not _matches(
        {
            "payment_status": "completed",
            "status": {"type": "accepted"},
            "custom_status": "refunded",
        }
    )


def test_status_cancelled_does_not_count():
    assert not _matches(
        {
            "payment_status": "completed",
            "status": {"type": "cancelled"},
        }
    )
