"""Which orders count as revenue on the admin dashboard.

`status.type` never used to include cancelled/refunded — those live on
`shipment_status` (Shiprocket cancel) and `custom_status` (admin refund tag).
Filters that only look at `status.type` keep counting that money.
"""

EXCLUDED_STATUS_TYPES = frozenset(
    {
        "rejected",
        "rejected_by_user",
        "cancelled",
        "cancellation_requested",
        "refunded",
        "refund_requested",
    }
)
EXCLUDED_SHIPMENT_STATUSES = frozenset({"cancelled", "cancellation_requested"})
EXCLUDED_CUSTOM_STATUSES = frozenset({"refunded", "refund_requested"})


def revenue_mongo_match() -> dict:
    return {
        "payment_status": "completed",
        "status.type": {"$nin": sorted(EXCLUDED_STATUS_TYPES)},
        "shipment_status": {"$nin": sorted(EXCLUDED_SHIPMENT_STATUSES)},
        "custom_status": {"$nin": sorted(EXCLUDED_CUSTOM_STATUSES)},
    }
