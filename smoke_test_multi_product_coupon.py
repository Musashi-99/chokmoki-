"""Standalone smoke test for multi-product discount coupons.

Run directly (no pytest/DB required):
    python smoke_test_multi_product_coupon.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")

from pydantic import ValidationError

from src.models.coupon import Coupon, CouponCreate, DiscountIndicator, DiscountType
from src.services.discount_service import CouponService, DiscountService, compute_discount

results: list[tuple[str, bool, str]] = []


def check(name: str, fn):
    try:
        fn()
        results.append((name, True, ""))
    except Exception as e:  # noqa: BLE001
        results.append((name, False, f"{e}\n{traceback.format_exc()}"))


def _item(product_id: str, total_price: float) -> SimpleNamespace:
    return SimpleNamespace(product_id=product_id, total_price=total_price)


def step1_coupon_create_validation():
    coupon = CouponCreate(
        code="MULTI10",
        type=DiscountType.PRODUCT,
        amount=10,
        indicator=DiscountIndicator.PERCENT,
        product_ids=["p1", "p2"],
    )
    assert coupon.product_ids == ["p1", "p2"], coupon.product_ids

    try:
        CouponCreate(
            code="EMPTY",
            type=DiscountType.PRODUCT,
            amount=10,
            indicator=DiscountIndicator.PERCENT,
            product_ids=[],
        )
        raise AssertionError("empty product_ids should have raised")
    except ValidationError:
        pass


def step2_compute_discount_multi_product():
    items = [_item("p1", 1000), _item("p2", 1000), _item("p3", 3000)]
    coupon = CouponCreate(
        code="MULTI10",
        type=DiscountType.PRODUCT,
        amount=10,
        indicator=DiscountIndicator.PERCENT,
        product_ids=["p1", "p2"],
    )
    computed, total, subtotal = compute_discount(items, coupon)
    assert subtotal == 5000, subtotal
    assert computed == 200, computed  # 10% of (1000 + 1000)
    assert total == 4800, total


def step3_compute_discount_no_match_raises():
    items = [_item("p3", 3000)]
    coupon = CouponCreate(
        code="MULTI10",
        type=DiscountType.PRODUCT,
        amount=10,
        indicator=DiscountIndicator.PERCENT,
        product_ids=["p1", "p2"],
    )
    try:
        compute_discount(items, coupon)
        raise AssertionError("should have raised for non-matching cart")
    except ValueError as e:
        assert "Coupon does not apply to this cart" in str(e), str(e)


def step4_discount_service_apply():
    async def run():
        items = [_item("p1", 1000), _item("p2", 1000), _item("p3", 3000)]
        coupon = Coupon(
            code="MULTI10",
            type=DiscountType.PRODUCT,
            amount=10,
            indicator=DiscountIndicator.PERCENT,
            active=True,
            product_ids=["p1", "p2"],
        )
        with patch.object(CouponService, "get_by_code", new_callable=AsyncMock, return_value=coupon):
            pricing, applied = await DiscountService().apply("MULTI10", items, shipping=0)
        assert pricing.subtotal == 5000, pricing.subtotal
        assert pricing.discount == 200, pricing.discount
        assert pricing.total == 4800, pricing.total
        assert applied is not None
        assert applied.product_ids == ["p1", "p2"], applied.product_ids

    asyncio.run(run())


def step5_legacy_doc_compat():
    coupon = Coupon(
        code="LEGACY",
        type=DiscountType.PRODUCT,
        amount=10,
        indicator=DiscountIndicator.PERCENT,
        active=True,
        product_id="legacy-single",
    )
    assert coupon.product_ids == ["legacy-single"], coupon.product_ids


def main():
    check("1. CouponCreate accepts multi product_ids / rejects empty list", step1_coupon_create_validation)
    check("2. compute_discount discounts only the listed products", step2_compute_discount_multi_product)
    check("3. compute_discount raises when cart has none of the products", step3_compute_discount_no_match_raises)
    check("4. DiscountService.apply returns correct pricing + snapshot", step4_discount_service_apply)
    check("5. Legacy single product_id doc loads as product_ids list", step5_legacy_doc_compat)

    print("\n=== Multi-product coupon smoke test ===")
    failed = 0
    for name, ok, err in results:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        if not ok:
            failed += 1
            print(err)

    print(f"\n{len(results) - failed}/{len(results)} checks passed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
