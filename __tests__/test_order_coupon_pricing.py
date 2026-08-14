from __future__ import annotations

import json
import os
import sys
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")

from src.models.coupon import Coupon, DiscountIndicator, DiscountType
from src.models.order import OrderCreateInput
from src.services.discount_service import CouponService, compute_discount
from src.services.order_service import OrderService


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value
        self.ttls[key] = ttl

    async def set(self, key: str, value: str, keepttl: bool = False, **_kwargs):
        self.store[key] = value
        return True


def _catalog_product(product_id: str = "p1", price: float = 2000):
    return SimpleNamespace(
        id=product_id,
        name="Ring",
        price_inr=price,
        active=True,
        product_variants=[],
    )


def _cart_percent_coupon(code: str = "SAVE10", amount: float = 10) -> Coupon:
    return Coupon(
        code=code,
        type=DiscountType.CART,
        amount=amount,
        indicator=DiscountIndicator.PERCENT,
        active=True,
        product_id=None,
    )


def _product_coupon(product_id: str, code: str = "PROD10") -> Coupon:
    return Coupon(
        code=code,
        type=DiscountType.PRODUCT,
        amount=10,
        indicator=DiscountIndicator.PERCENT,
        active=True,
        product_id=product_id,
    )


def _order_payload(**overrides):
    payload = {
        "shippingAddress": {
            "email": "x@test.com",
            "full_name": "X",
            "phone": "9999999999",
            "address_line1": "a",
            "address_line2": "",
            "city": "c",
            "state": "s",
            "postal_code": "1",
            "country": "IN",
            "is_default": False,
        },
        "items": [
            {
                "productId": "p1",
                "productName": "Ring",
                "variant": {"default": "default"},
                "quantity": 1,
                "price": 2000,
                "total": 2000,
            }
        ],
        "specialMessage": "",
        "pricing": {"subtotal": 2000, "discount": 0, "shipping": 0, "total": 2000},
        "userEmail": "x@test.com",
        "timestamp": "2026-08-15T00:00:00Z",
        "paymentMethod": "cod",
    }
    payload.update(overrides)
    return payload


async def _run_guarded(*, fn, **_kwargs):
    return await fn()


@contextmanager
def order_pipeline_mocks(coupon=None, product=None):
    product = product or _catalog_product()
    mock_ps = MagicMock()
    mock_ps.get_by_id = AsyncMock(return_value=product)

    orders_col = AsyncMock()
    orders_col.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=ObjectId()))
    logs_col = AsyncMock()
    logs_col.insert_one = AsyncMock()
    database = MagicMock()
    database.__getitem__ = MagicMock(
        side_effect=lambda name: orders_col if name == "orders" else logs_col
    )

    fake_redis = FakeRedis()

    with ExitStack() as stack:
        stack.enter_context(patch("src.services.order_service.ProductService", return_value=mock_ps))
        stack.enter_context(
            patch.object(CouponService, "get_by_code", new_callable=AsyncMock, return_value=coupon)
        )
        inv_cls = stack.enter_context(patch("src.services.order_service.InventoryService"))
        inv_cls.return_value.commit_items = AsyncMock()
        inv_cls.return_value.reserve_for_order = AsyncMock()
        stack.enter_context(
            patch(
                "src.database.connection.db.get_database",
                new_callable=AsyncMock,
                return_value=database,
            )
        )
        stack.enter_context(
            patch(
                "src.services.order_service.FraudEnrichmentService.mark_order_completed",
                new_callable=AsyncMock,
            )
        )
        stack.enter_context(
            patch(
                "src.services.order_service.redis_client.get_client",
                new_callable=AsyncMock,
                return_value=fake_redis,
            )
        )
        razorpay_cls = stack.enter_context(patch("src.services.order_service.RazorpayService"))
        razorpay_cls.return_value.create_order.return_value = SimpleNamespace(id="rzp_order_1")
        stack.enter_context(patch("src.services.order_service.call_guarded", new=_run_guarded))
        recon_cls = stack.enter_context(
            patch("src.services.order_service.PaymentReconciliationService")
        )
        recon_cls.return_value.record_attempt = AsyncMock()
        yield SimpleNamespace(
            orders=orders_col,
            logs=logs_col,
            razorpay=razorpay_cls,
            redis=fake_redis,
            inventory=inv_cls,
        )


class TestOrderCouponPricing:
    @pytest.mark.asyncio
    async def test_cod_create_cart_percent_persists_snapshot(self):
        coupon = _cart_percent_coupon()
        expected_computed, expected_total, expected_subtotal = compute_discount(
            [SimpleNamespace(product_id="p1", total_price=2000)], coupon
        )
        order_data = OrderCreateInput(**_order_payload(couponCode="SAVE10"))

        with order_pipeline_mocks(coupon=coupon) as mocks:
            order = await OrderService().create(order_data)

        mocks.orders.insert_one.assert_awaited_once()
        doc = mocks.orders.insert_one.call_args.args[0]
        assert doc["subtotal"] == expected_subtotal
        assert doc["discount"] == expected_computed
        assert doc["total_amount"] == expected_total
        assert doc["applied_discount"]["code"] == "SAVE10"
        assert order.applied_discount is not None
        assert order.applied_discount.code == "SAVE10"
        assert order.discount == expected_computed
        assert order.total_amount == expected_total

    @pytest.mark.asyncio
    async def test_initiate_order_razorpay_uses_discounted_total(self):
        coupon = _cart_percent_coupon()
        expected_computed, expected_total, _ = compute_discount(
            [SimpleNamespace(product_id="p1", total_price=2000)], coupon
        )
        order_data = OrderCreateInput(
            **_order_payload(couponCode="SAVE10", paymentMethod="razorpay")
        )

        with order_pipeline_mocks(coupon=coupon) as mocks:
            result = await OrderService().initiate_order(order_data)

        mocks.razorpay.return_value.create_order.assert_called_once()
        assert mocks.razorpay.return_value.create_order.call_args.kwargs["amount"] == expected_total
        assert result.amount == expected_total
        pending_raw = next(
            value for key, value in mocks.redis.store.items() if key.startswith("pending_order:")
        )
        pending = json.loads(pending_raw)
        assert pending["discount"] == expected_computed
        assert pending["total_amount"] == expected_total
        assert pending["applied_discount"]["code"] == "SAVE10"

    @pytest.mark.asyncio
    async def test_invalid_code_raises_and_does_not_insert(self):
        order_data = OrderCreateInput(**_order_payload(couponCode="NOPE"))

        with order_pipeline_mocks(coupon=None) as mocks:
            with pytest.raises(ValueError, match="Invalid coupon"):
                await OrderService().create(order_data)

        mocks.orders.insert_one.assert_not_called()
        mocks.inventory.return_value.commit_items.assert_not_called()

    @pytest.mark.asyncio
    async def test_product_coupon_wrong_product_raises(self):
        coupon = _product_coupon(product_id="other")
        order_data = OrderCreateInput(**_order_payload(couponCode="PROD10"))

        with order_pipeline_mocks(coupon=coupon) as mocks:
            with pytest.raises(ValueError, match="Coupon does not apply to this cart"):
                await OrderService().create(order_data)

        mocks.orders.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_coupon_omits_applied_discount_and_zero_discount(self):
        order_data = OrderCreateInput(**_order_payload())

        with order_pipeline_mocks(coupon=None) as mocks:
            order = await OrderService().create(order_data)

        doc = mocks.orders.insert_one.call_args.args[0]
        assert "applied_discount" not in doc
        assert doc["discount"] == 0
        assert doc["total_amount"] == 2000
        assert order.applied_discount is None
        assert order.discount == 0

    @pytest.mark.asyncio
    async def test_client_pricing_discount_ignored_without_code(self):
        order_data = OrderCreateInput(
            **_order_payload(
                pricing={"subtotal": 2000, "discount": 9999, "shipping": 0, "total": 1}
            )
        )

        with order_pipeline_mocks(coupon=None) as mocks:
            order = await OrderService().create(order_data)

        doc = mocks.orders.insert_one.call_args.args[0]
        assert "applied_discount" not in doc
        assert doc["discount"] == 0
        assert doc["total_amount"] == 2000
        assert order.discount == 0
        assert order.total_amount == 2000
