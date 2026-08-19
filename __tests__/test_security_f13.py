"""F-13 — Webhook-secret / lost-webhook order reconciliation.

Vulnerability: paid Razorpay orders live in Redis as ``pending_order:<id>`` until
the ``payment.captured`` webhook persists them to Mongo. If
``RAZORPAY_WEBHOOK_SECRET`` is unset/misconfigured (``verify_webhook_signature``
returns False) or the webhook is simply dropped, the captured payment is never
persisted and the order is deleted when its Redis TTL expires — the customer is
charged but the order is lost.

Fix: an authenticated reconciliation job (``/cron/orders/reconcile`` →
``OrderService.reconcile_pending_payments``) that asks Razorpay for the
authoritative payment state of pending orders and persists any captured ones.
Idempotent via the unique ``order_id`` upsert in ``complete_pending_order``.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import types
from unittest.mock import AsyncMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.services.order_service import OrderService
from src.services.razorpay_service import RazorpayService


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeScanRedis:
    """Minimal async Redis double supporting scan_iter + get."""

    def __init__(self, store: dict[str, str]) -> None:
        self.store = store

    async def scan_iter(self, match: str = "*", count: int = 100):
        prefix = match.rstrip("*")
        for key in list(self.store.keys()):
            if key.startswith(prefix):
                yield key

    async def get(self, key: str):
        return self.store.get(key)

    async def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    async def delete(self, *keys: str):
        for key in keys:
            self.store.pop(key, None)

    async def getdel(self, key: str):
        return self.store.pop(key, None)


class FakeRazorpay:
    def __init__(self, captured: dict[str, dict | None]) -> None:
        # map razorpay_order_id -> payment dict (or None)
        self._captured = captured

    def fetch_captured_payment(self, razorpay_order_id: str):
        return self._captured.get(razorpay_order_id)


def _pending(order_id: str, rzp_order_id: str | None, method: str = "razorpay") -> str:
    doc = {
        "order_id": order_id,
        "payment_method": method,
        "total_amount": 1000.0,
    }
    if rzp_order_id is not None:
        doc["razorpay_order_id"] = rzp_order_id
    return json.dumps(doc)


# --------------------------------------------------------------------------- #
# Unit — RazorpayService.fetch_captured_payment
# --------------------------------------------------------------------------- #
class TestFetchCapturedPayment:
    def _service(self):
        with patch("src.services.razorpay_service.razorpay.Client"):
            return RazorpayService()

    def test_returns_captured_payment(self):
        service = self._service()
        service.client.order.payments = lambda oid: {
            "items": [
                {"id": "pay_1", "status": "failed", "amount": 100000},
                {"id": "pay_2", "status": "captured", "amount": 100000},
            ]
        }
        result = service.fetch_captured_payment("order_rzp_1")
        assert result == {"id": "pay_2", "status": "captured", "amount_inr": 1000.0}

    def test_returns_none_when_no_capture(self):
        service = self._service()
        service.client.order.payments = lambda oid: {
            "items": [{"id": "pay_1", "status": "failed", "amount": 100000}]
        }
        assert service.fetch_captured_payment("order_rzp_1") is None

    def test_returns_none_on_api_error(self):
        service = self._service()

        def boom(oid):
            raise RuntimeError("razorpay down")

        service.client.order.payments = boom
        assert service.fetch_captured_payment("order_rzp_1") is None


# --------------------------------------------------------------------------- #
# Integration — reconcile_pending_payments
# --------------------------------------------------------------------------- #
class TestReconcilePendingPayments:
    @pytest.mark.asyncio
    async def test_recovers_captured_order(self, monkeypatch):
        store = {"pending_order:o1": _pending("o1", "rzp_o1")}
        fake_redis = FakeScanRedis(store)
        fake_rzp = FakeRazorpay({"rzp_o1": {"id": "pay_x", "status": "captured", "amount_inr": 1000.0}})

        monkeypatch.setattr(
            "src.services.order_service.redis_client.get_client",
            AsyncMock(return_value=fake_redis),
        )
        monkeypatch.setattr(
            "src.services.order_service.RazorpayService", lambda: fake_rzp
        )

        service = OrderService()
        complete = AsyncMock(return_value=(object(), "created"))
        monkeypatch.setattr(service, "complete_pending_order", complete)

        summary = await service.reconcile_pending_payments()

        complete.assert_awaited_once_with("o1", "rzp_o1", "pay_x")
        assert summary == {"checked": 1, "recovered": 1, "still_pending": 0, "errors": 0}

    @pytest.mark.asyncio
    async def test_skips_uncaptured_order(self, monkeypatch):
        store = {"pending_order:o2": _pending("o2", "rzp_o2")}
        fake_redis = FakeScanRedis(store)
        fake_rzp = FakeRazorpay({"rzp_o2": None})

        monkeypatch.setattr(
            "src.services.order_service.redis_client.get_client",
            AsyncMock(return_value=fake_redis),
        )
        monkeypatch.setattr(
            "src.services.order_service.RazorpayService", lambda: fake_rzp
        )

        service = OrderService()
        complete = AsyncMock()
        monkeypatch.setattr(service, "complete_pending_order", complete)

        summary = await service.reconcile_pending_payments()

        complete.assert_not_awaited()
        assert summary["checked"] == 1
        assert summary["recovered"] == 0
        assert summary["still_pending"] == 1

    @pytest.mark.asyncio
    async def test_skips_cod_and_missing_rzp_id(self, monkeypatch):
        store = {
            "pending_order:cod1": _pending("cod1", None, method="cod"),
            "pending_order:legacy": _pending("legacy", None),  # razorpay, pre-F-13
        }
        fake_redis = FakeScanRedis(store)
        fake_rzp = FakeRazorpay({})

        monkeypatch.setattr(
            "src.services.order_service.redis_client.get_client",
            AsyncMock(return_value=fake_redis),
        )
        monkeypatch.setattr(
            "src.services.order_service.RazorpayService", lambda: fake_rzp
        )

        service = OrderService()
        complete = AsyncMock()
        monkeypatch.setattr(service, "complete_pending_order", complete)

        summary = await service.reconcile_pending_payments()

        complete.assert_not_awaited()
        # cod skipped entirely (not counted); legacy razorpay w/o id -> still_pending
        assert summary["checked"] == 0
        assert summary["still_pending"] == 1

    @pytest.mark.asyncio
    async def test_counts_errors_without_aborting(self, monkeypatch):
        store = {
            "pending_order:oa": _pending("oa", "rzp_a"),
            "pending_order:ob": _pending("ob", "rzp_b"),
        }
        fake_redis = FakeScanRedis(store)
        fake_rzp = FakeRazorpay(
            {
                "rzp_a": {"id": "pay_a", "status": "captured", "amount_inr": 1000.0},
                "rzp_b": {"id": "pay_b", "status": "captured", "amount_inr": 1000.0},
            }
        )

        monkeypatch.setattr(
            "src.services.order_service.redis_client.get_client",
            AsyncMock(return_value=fake_redis),
        )
        monkeypatch.setattr(
            "src.services.order_service.RazorpayService", lambda: fake_rzp
        )

        service = OrderService()

        async def flaky(order_id, *_args):
            if order_id == "oa":
                raise RuntimeError("mongo blip")
            return (object(), "created")

        monkeypatch.setattr(service, "complete_pending_order", flaky)

        summary = await service.reconcile_pending_payments()

        assert summary["checked"] == 2
        assert summary["recovered"] == 1
        assert summary["errors"] == 1


# --------------------------------------------------------------------------- #
# Route — /cron/orders/reconcile auth + wiring
# --------------------------------------------------------------------------- #
def _stub_external_modules() -> None:
    telegram = types.ModuleType("telegram")
    telegram.Bot = object
    telegram_error = types.ModuleType("telegram.error")
    telegram_error.TelegramError = Exception
    telegram_error.NetworkError = Exception
    telegram_error.RetryAfter = Exception
    telegram_error.TimedOut = Exception
    boto3 = types.ModuleType("boto3")
    boto3.client = lambda *a, **k: object()
    botocore = types.ModuleType("botocore")
    botocore_client = types.ModuleType("botocore.client")
    botocore_client.Config = object
    botocore.client = botocore_client
    sys.modules.update(
        {
            "telegram": telegram,
            "telegram.error": telegram_error,
            "boto3": boto3,
            "botocore": botocore,
            "botocore.client": botocore_client,
        }
    )


@pytest.fixture
def api_module(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.delenv("CRON_SECRET", raising=False)
    _stub_external_modules()

    # Snapshot the currently-imported modules before popping them so they
    # can be restored afterwards. Other test files import symbols from
    # these modules at collection time (before any test runs); leaving the
    # freshly-reloaded replacements in sys.modules after this fixture tears
    # down corrupts unittest.mock.patch() targets in every later test that
    # references the original module objects (e.g. test_storefront_caching.py).
    affected_names = {"api.index", "api.bootstrap", "src.config"} | {
        name for name in sys.modules if name.startswith("api.routes")
    }
    saved_modules = {name: sys.modules[name] for name in affected_names if name in sys.modules}
    try:
        for name in affected_names:
            sys.modules.pop(name, None)
        api_module = importlib.import_module("api.index")
        from api import bootstrap

        if bootstrap.settings is not None:
            bootstrap.settings.cron_secret = None
        yield api_module
    finally:
        for name in list(sys.modules):
            if name in ("api.index", "api.bootstrap", "src.config") or name.startswith("api.routes"):
                if name not in saved_modules:
                    sys.modules.pop(name, None)
        sys.modules.update(saved_modules)


class TestReconcileCronRoute:
    def test_route_registered(self, api_module):
        paths = {route.path for route in api_module.app.routes}
        assert "/cron/orders/reconcile" in paths

    def test_dev_no_secret_runs(self, api_module):
        from fastapi.testclient import TestClient

        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha")
        mock_redis.evalsha = AsyncMock(return_value=[1, 0])

        summary = {"checked": 0, "recovered": 0, "still_pending": 0, "errors": 0}
        with patch(
            "src.plugins.rate_limit.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ), patch.object(
            api_module.OrderService,
            "reconcile_pending_payments",
            new=AsyncMock(return_value=summary),
        ):
            client = TestClient(api_module.app, raise_server_exceptions=True)
            response = client.post("/cron/orders/reconcile")

        assert response.status_code == 200
        assert response.json() == summary

    def test_dev_with_secret_requires_header(self, api_module, monkeypatch):
        from fastapi.testclient import TestClient

        # Set the secret on the already-loaded settings instance.
        api_module.settings.cron_secret = "topsecret"

        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha")
        mock_redis.evalsha = AsyncMock(return_value=[1, 0])

        with patch(
            "src.plugins.rate_limit.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            client = TestClient(api_module.app, raise_server_exceptions=True)
            response = client.post("/cron/orders/reconcile")  # no header

        assert response.status_code == 401
