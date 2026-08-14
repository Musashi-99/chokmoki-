"""F-05 inventory reservations, atomic decrements, and oversell prevention."""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.order import ValidatedOrderItem
from src.services.inventory_service import InventoryService


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(
        self,
        key: str,
        value: str,
        nx: bool = False,
        ex: int | None = None,
        keepttl: bool = False,
    ):
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        # keepttl preserves any existing TTL (no-op for this double)
        return True

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value
        self.ttls[key] = ttl

    async def delete(self, *keys: str):
        for key in keys:
            self.store.pop(key, None)
            self.ttls.pop(key, None)

    async def incrby(self, key: str, amount: int):
        current = int(self.store.get(key, 0))
        current += amount
        self.store[key] = str(current)
        return current

    async def decrby(self, key: str, amount: int):
        current = int(self.store.get(key, 0))
        current -= amount
        self.store[key] = str(current)
        return current

    async def ttl(self, key: str):
        if key not in self.store:
            return -2
        return self.ttls.get(key, -1)

    async def scan_iter(self, match: str | None = None):
        prefix = (match or "").rstrip("*")
        for key in list(self.store.keys()):
            if key.startswith(prefix):
                yield key


def _item(product_id: str, quantity: int = 1) -> ValidatedOrderItem:
    return ValidatedOrderItem(
        product_id=product_id,
        product_name="Test",
        variant={"default": "default"},
        quantity=quantity,
        unit_price=100.0,
        total_price=100.0 * quantity,
    )


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def product_id():
    return str(ObjectId())


class TestInventoryTracking:
    def test_unlimited_when_stock_qty_missing(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        service = InventoryService()
        assert service.tracks_inventory(None) is False
        assert service.tracks_inventory(10) is True

    def test_disabled_inventory_flag(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

        service = InventoryService()
        with patch("src.services.inventory_service.settings") as mock_settings:
            mock_settings.inventory_enabled = False
            assert service.tracks_inventory(5) is False


class TestInventoryReserveAndRelease:
    @pytest.mark.asyncio
    async def test_reserve_and_release_pending_qty(
        self, monkeypatch, fake_redis, product_id
    ):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

        service = InventoryService()
        order_id = "order-1"

        with patch(
            "src.services.inventory_service.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=fake_redis,
        ), patch.object(
            service, "_get_stock_qty", new_callable=AsyncMock, return_value=5
        ):
            await service.reserve_for_order(order_id, [_item(product_id, 2)])

        assert fake_redis.store[f"inv:pending:{product_id}"] == "2"
        assert json.loads(fake_redis.store[f"inv:order:{order_id}"])[0]["quantity"] == 2

        with patch(
            "src.services.inventory_service.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=fake_redis,
        ):
            await service.release_reservation(order_id)

        assert f"inv:pending:{product_id}" not in fake_redis.store
        assert f"inv:order:{order_id}" not in fake_redis.store

    @pytest.mark.asyncio
    async def test_reserve_rejects_oversell(
        self, monkeypatch, fake_redis, product_id
    ):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

        service = InventoryService()
        fake_redis.store[f"inv:pending:{product_id}"] = "4"

        with patch(
            "src.services.inventory_service.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=fake_redis,
        ), patch.object(
            service, "_get_stock_qty", new_callable=AsyncMock, return_value=5
        ):
            with pytest.raises(ValueError, match="Insufficient stock"):
                await service.reserve_for_order("order-2", [_item(product_id, 2)])

        assert f"inv:order:order-2" not in fake_redis.store
        assert fake_redis.store[f"inv:pending:{product_id}"] == "4"

    @pytest.mark.asyncio
    async def test_skips_untracked_products(self, monkeypatch, fake_redis, product_id):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

        service = InventoryService()

        with patch(
            "src.services.inventory_service.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=fake_redis,
        ), patch.object(
            service, "_get_stock_qty", new_callable=AsyncMock, return_value=None
        ):
            await service.reserve_for_order("order-3", [_item(product_id, 1)])

        assert fake_redis.store == {}


class TestInventoryCommit:
    @pytest.mark.asyncio
    async def test_commit_reservation_decrements_mongo(
        self, monkeypatch, fake_redis, product_id
    ):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

        service = InventoryService()
        order_id = "order-paid"
        fake_redis.store[f"inv:order:{order_id}"] = json.dumps(
            [{"product_id": product_id, "quantity": 2}]
        )
        fake_redis.store[f"inv:pending:{product_id}"] = "2"

        with patch(
            "src.services.inventory_service.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=fake_redis,
        ), patch.object(
            service, "_atomic_decrement", new_callable=AsyncMock, return_value=True
        ) as decrement:
            await service.commit_reservation(order_id)

        decrement.assert_awaited_once_with(product_id, 2)
        assert f"inv:order:{order_id}" not in fake_redis.store
        assert f"inv:pending:{product_id}" not in fake_redis.store

    @pytest.mark.asyncio
    async def test_commit_items_rejects_when_decrement_fails(
        self, monkeypatch, product_id
    ):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

        service = InventoryService()

        with patch.object(
            service, "_get_stock_qty", new_callable=AsyncMock, return_value=1
        ), patch.object(
            service, "_atomic_decrement", new_callable=AsyncMock, return_value=False
        ):
            with pytest.raises(ValueError, match="Insufficient stock"):
                await service.commit_items([_item(product_id, 2)])


class TestInventoryReconcile:
    @pytest.mark.asyncio
    async def test_reconcile_releases_near_expiry(self, monkeypatch, fake_redis, product_id):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

        service = InventoryService()
        fake_redis.store["inv:order:stale-order"] = json.dumps(
            [{"product_id": product_id, "quantity": 1}]
        )
        fake_redis.store[f"inv:pending:{product_id}"] = "1"
        fake_redis.ttls["inv:order:stale-order"] = 30
        fake_redis.store["inv:order:fresh-order"] = json.dumps(
            [{"product_id": product_id, "quantity": 1}]
        )
        fake_redis.ttls["inv:order:fresh-order"] = 600

        with patch(
            "src.services.inventory_service.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=fake_redis,
        ):
            released = await service.reconcile_stale_reservations()

        assert released == 1
        assert "inv:order:stale-order" not in fake_redis.store
        assert "inv:order:fresh-order" in fake_redis.store


class TestOrderServiceInventoryHooks:
    @pytest.mark.asyncio
    async def test_initiate_order_reserves_inventory(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

        from src.fraud.models import FraudAction, FraudDecision
        from src.models.order import OrderCreateInput
        from src.services.order_service import OrderService

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
                    "productName": "n",
                    "variant": {"default": "default"},
                    "quantity": 1,
                    "price": 100,
                    "total": 100,
                }
            ],
            "specialMessage": "",
            "pricing": {"subtotal": 100, "discount": 0, "shipping": 0, "total": 100},
            "userEmail": "x@test.com",
            "timestamp": "2026-06-30T00:00:00Z",
            "paymentMethod": "razorpay",
        }
        order_data = OrderCreateInput(**payload)
        validated = [_item("p1", 1)]
        pricing = SimpleNamespace(subtotal=100, discount=0, shipping=0, total=100)

        service = OrderService()
        reserve_mock = AsyncMock()
        fake_redis = FakeRedis()

        allow_decision = FraudDecision(
            action=FraudAction.ALLOW,
            risk_score=0,
            confidence=0,
            matched=[],
            rule_set_id="t",
            rule_set_version="1",
        )

        with patch.object(
            service, "_validate_and_prepare_order", new_callable=AsyncMock, return_value=(validated, pricing, None)
        ), patch(
            "src.services.order_service.FraudDetectionService.evaluate",
            new_callable=AsyncMock,
            return_value=allow_decision,
        ), patch(
            "src.services.order_service.InventoryService",
        ) as inventory_cls, patch(
            "src.services.order_service.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=fake_redis,
        ), patch(
            "src.services.order_service.RazorpayService"
        ) as razorpay_cls:
            inventory_cls.return_value.reserve_for_order = reserve_mock
            razorpay_cls.return_value.create_order.return_value = SimpleNamespace(
                id="rzp_order_1"
            )
            result = await service.initiate_order(order_data)

        reserve_mock.assert_awaited_once()
        assert result.razorpay_order_id == "rzp_order_1"

    @pytest.mark.asyncio
    async def test_clear_pending_releases_reservation(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

        from src.services.order_service import OrderService

        service = OrderService()
        fake_redis = FakeRedis()
        release_mock = AsyncMock()

        with patch(
            "src.services.order_service.InventoryService",
        ) as inventory_cls, patch(
            "src.services.order_service.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=fake_redis,
        ):
            inventory_cls.return_value.release_reservation = release_mock
            await service._clear_pending_redis("order-x")

        release_mock.assert_awaited_once_with("order-x")
        assert "pending_order:order-x" not in fake_redis.store
