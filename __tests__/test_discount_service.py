from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.coupon import (
    CouponCreate,
    DiscountIndicator,
    DiscountType,
)
from src.services.discount_service import compute_discount


def _item(product_id: str, total_price: float) -> SimpleNamespace:
    return SimpleNamespace(product_id=product_id, total_price=total_price)


def _cart_amount(amount: float, **kwargs) -> CouponCreate:
    return CouponCreate(
        code="SAVE500",
        type=DiscountType.CART,
        amount=amount,
        indicator=DiscountIndicator.AMOUNT,
        **kwargs,
    )


def _cart_percent(amount: float, code: str = "SAVE10") -> CouponCreate:
    return CouponCreate(
        code=code,
        type=DiscountType.CART,
        amount=amount,
        indicator=DiscountIndicator.PERCENT,
    )


def _product_coupon(amount: float, indicator: DiscountIndicator, product_id: str) -> CouponCreate:
    return CouponCreate(
        code="PROD10",
        type=DiscountType.PRODUCT,
        amount=amount,
        indicator=indicator,
        product_id=product_id,
    )


class TestComputeDiscount:
    def test_cart_amount_500_on_subtotal_2000(self):
        items = [_item("p1", 2000)]
        computed, total, subtotal = compute_discount(items, _cart_amount(500))
        assert subtotal == 2000
        assert computed == 500
        assert total == 1500

    def test_cart_amount_5000_capped_at_subtotal(self):
        items = [_item("p1", 2000)]
        computed, total, subtotal = compute_discount(items, _cart_amount(5000))
        assert subtotal == 2000
        assert computed == 2000
        assert total == 0

    def test_cart_percent_10_on_4999(self):
        items = [_item("p1", 4999)]
        computed, total, subtotal = compute_discount(items, _cart_percent(10))
        assert subtotal == 4999
        assert computed == 499.90
        assert total == 4499.10

    def test_product_percent_10_matching_line_only(self):
        items = [_item("match", 2000), _item("other", 3000)]
        coupon = _product_coupon(10, DiscountIndicator.PERCENT, "match")
        computed, total, subtotal = compute_discount(items, coupon)
        assert subtotal == 5000
        assert computed == 200
        assert total == 4800

    def test_product_amount_500_capped_at_matching_line(self):
        items = [_item("match", 200), _item("other", 3000)]
        coupon = _product_coupon(500, DiscountIndicator.AMOUNT, "match")
        computed, total, subtotal = compute_discount(items, coupon)
        assert subtotal == 3200
        assert computed == 200
        assert total == 3000

    def test_product_not_in_items_raises(self):
        items = [_item("other", 3000)]
        coupon = _product_coupon(10, DiscountIndicator.PERCENT, "missing")
        with pytest.raises(ValueError, match="Coupon does not apply to this cart"):
            compute_discount(items, coupon)

    def test_shipping_never_discounted(self):
        items = [_item("p1", 2000)]
        computed, total, subtotal = compute_discount(items, _cart_amount(500), shipping=150)
        assert subtotal == 2000
        assert computed == 500
        assert total == 1650

    def test_shipping_added_when_discount_caps_subtotal(self):
        items = [_item("p1", 2000)]
        computed, total, subtotal = compute_discount(items, _cart_amount(5000), shipping=80)
        assert subtotal == 2000
        assert computed == 2000
        assert total == 80


class TestCouponCreate:
    def test_percent_amount_0_rejected(self):
        with pytest.raises(ValidationError):
            CouponCreate(
                code="PCT0",
                type=DiscountType.CART,
                amount=0,
                indicator=DiscountIndicator.PERCENT,
            )

    def test_percent_amount_101_rejected(self):
        with pytest.raises(ValidationError):
            CouponCreate(
                code="PCT101",
                type=DiscountType.CART,
                amount=101,
                indicator=DiscountIndicator.PERCENT,
            )

    def test_amount_zero_rejected(self):
        with pytest.raises(ValidationError):
            CouponCreate(
                code="AMT0",
                type=DiscountType.CART,
                amount=0,
                indicator=DiscountIndicator.AMOUNT,
            )

    def test_amount_negative_rejected(self):
        with pytest.raises(ValidationError):
            CouponCreate(
                code="AMTNEG",
                type=DiscountType.CART,
                amount=-1,
                indicator=DiscountIndicator.AMOUNT,
            )

    def test_product_without_product_id_rejected(self):
        with pytest.raises(ValidationError):
            CouponCreate(
                code="NOPROD",
                type=DiscountType.PRODUCT,
                amount=10,
                indicator=DiscountIndicator.PERCENT,
            )

    def test_product_empty_product_id_rejected(self):
        with pytest.raises(ValidationError):
            CouponCreate(
                code="EMPTYID",
                type=DiscountType.PRODUCT,
                amount=10,
                indicator=DiscountIndicator.PERCENT,
                product_id="   ",
            )

    def test_cart_strips_product_id(self):
        coupon = CouponCreate(
            code="CARTID",
            type=DiscountType.CART,
            amount=500,
            indicator=DiscountIndicator.AMOUNT,
            product_id="should-be-ignored",
        )
        assert coupon.product_id is None

    def test_code_uppercased(self):
        coupon = CouponCreate(
            code="save10",
            type=DiscountType.CART,
            amount=10,
            indicator=DiscountIndicator.PERCENT,
        )
        assert coupon.code == "SAVE10"

    def test_code_too_short_rejected(self):
        with pytest.raises(ValidationError):
            CouponCreate(
                code="AB",
                type=DiscountType.CART,
                amount=10,
                indicator=DiscountIndicator.PERCENT,
            )

    def test_percent_100_accepted(self):
        coupon = CouponCreate(
            code="FREE100",
            type=DiscountType.CART,
            amount=100,
            indicator=DiscountIndicator.PERCENT,
        )
        assert coupon.amount == 100
