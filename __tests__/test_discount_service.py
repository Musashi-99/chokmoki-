from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.coupon import (
    Coupon,
    CouponCreate,
    CouponPreviewInput,
    DiscountIndicator,
    DiscountType,
)
from src.services.discount_service import CouponService, DiscountService, compute_discount


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


class TestCouponPreviewInput:
    def test_empty_items_rejected(self):
        with pytest.raises(ValidationError):
            CouponPreviewInput(code="SAVE10", items=[])

    def test_over_50_items_rejected(self):
        items = [{"productId": f"p{i}", "quantity": 1} for i in range(51)]
        with pytest.raises(ValidationError):
            CouponPreviewInput(code="SAVE10", items=items)


def _coupon(**kwargs) -> Coupon:
    defaults = dict(
        code="SAVE10",
        type=DiscountType.CART,
        amount=10,
        indicator=DiscountIndicator.PERCENT,
        active=True,
        product_id=None,
    )
    defaults.update(kwargs)
    return Coupon(**defaults)


class TestDiscountServiceApply:
    @pytest.mark.asyncio
    async def test_blank_code_zero_discount_no_applied(self):
        items = [_item("p1", 2000)]
        pricing, applied = await DiscountService().apply("", items, shipping=50)
        assert pricing.subtotal == 2000
        assert pricing.discount == 0
        assert pricing.shipping == 50
        assert pricing.total == 2050
        assert applied is None

    @pytest.mark.asyncio
    async def test_none_code_zero_discount_no_applied(self):
        items = [_item("p1", 2000)]
        pricing, applied = await DiscountService().apply(None, items)
        assert pricing.discount == 0
        assert pricing.total == 2000
        assert applied is None

    @pytest.mark.asyncio
    async def test_missing_coupon_raises_invalid(self):
        items = [_item("p1", 2000)]
        with patch.object(CouponService, "get_by_code", new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match="Invalid coupon"):
                await DiscountService().apply("NOPE", items)

    @pytest.mark.asyncio
    async def test_inactive_coupon_raises(self):
        items = [_item("p1", 2000)]
        coupon = _coupon(active=False)
        with patch.object(CouponService, "get_by_code", new_callable=AsyncMock, return_value=coupon):
            with pytest.raises(ValueError, match="Invalid coupon"):
                await DiscountService().apply("SAVE10", items)

    @pytest.mark.asyncio
    async def test_valid_cart_percent_snapshot_amount_is_configured(self):
        items = [_item("p1", 2000)]
        coupon = _coupon(code="SAVE10", amount=10, indicator=DiscountIndicator.PERCENT)
        with patch.object(CouponService, "get_by_code", new_callable=AsyncMock, return_value=coupon):
            pricing, applied = await DiscountService().apply("SAVE10", items)
        assert pricing.subtotal == 2000
        assert pricing.discount == 200
        assert pricing.shipping == 0
        assert pricing.total == 1800
        assert applied is not None
        assert applied.code == "SAVE10"
        assert applied.type == DiscountType.CART
        assert applied.amount == 10
        assert applied.indicator == DiscountIndicator.PERCENT
        assert not hasattr(applied, "product_id") or "product_id" not in applied.model_dump()

    @pytest.mark.asyncio
    async def test_product_miss_raises(self):
        items = [_item("other", 2000)]
        coupon = _coupon(
            type=DiscountType.PRODUCT,
            product_id="match",
            amount=10,
            indicator=DiscountIndicator.PERCENT,
        )
        with patch.object(CouponService, "get_by_code", new_callable=AsyncMock, return_value=coupon):
            with pytest.raises(ValueError, match="Coupon does not apply to this cart"):
                await DiscountService().apply("SAVE10", items)


class TestResolvePreviewItems:
    @pytest.mark.asyncio
    async def test_uses_catalog_price_times_quantity(self):
        product = SimpleNamespace(id="pid1", price_inr=1500, active=True)
        mock_svc = MagicMock()
        mock_svc.get_by_id = AsyncMock(return_value=product)
        with patch("src.services.product_service.ProductService", return_value=mock_svc):
            items = await DiscountService().resolve_preview_items(
                [SimpleNamespace(productId="pid1", quantity=2)]
            )
        assert items[0].product_id == "pid1"
        assert items[0].total_price == 3000
        mock_svc.get_by_id.assert_called_once_with("pid1")

    @pytest.mark.asyncio
    async def test_missing_product_raises(self):
        mock_svc = MagicMock()
        mock_svc.get_by_id = AsyncMock(return_value=None)
        with patch("src.services.product_service.ProductService", return_value=mock_svc):
            with pytest.raises(ValueError, match="not found"):
                await DiscountService().resolve_preview_items(
                    [SimpleNamespace(productId="missing", quantity=1)]
                )

    @pytest.mark.asyncio
    async def test_inactive_product_raises(self):
        product = SimpleNamespace(id="pid1", price_inr=1500, active=False)
        mock_svc = MagicMock()
        mock_svc.get_by_id = AsyncMock(return_value=product)
        with patch("src.services.product_service.ProductService", return_value=mock_svc):
            with pytest.raises(ValueError, match="is not active"):
                await DiscountService().resolve_preview_items(
                    [SimpleNamespace(productId="pid1", quantity=1)]
                )
