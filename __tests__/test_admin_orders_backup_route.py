"""Route wiring tests for GET /api/admin/orders/export and POST /api/admin/orders/import."""

from __future__ import annotations

import importlib
import json
import os
import sys
import types
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _stub_external_modules() -> None:
    telegram = types.ModuleType("telegram")
    telegram.Bot = object
    telegram_error = types.ModuleType("telegram.error")
    telegram_error.TelegramError = Exception
    boto3 = types.ModuleType("boto3")
    boto3.client = lambda *args, **kwargs: object()
    botocore = types.ModuleType("botocore")
    botocore_client = types.ModuleType("botocore.client")
    botocore_client.Config = object
    botocore.client = botocore_client
    sys.modules["telegram"] = telegram
    sys.modules["telegram.error"] = telegram_error
    sys.modules["boto3"] = boto3
    sys.modules["botocore"] = botocore
    sys.modules["botocore.client"] = botocore_client


def _minimal_backup_json() -> bytes:
    return json.dumps({"orders": [{"order_id": "ORD-1"}], "order_logs": []}).encode("utf-8")


@pytest.fixture
def api_module(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
    _stub_external_modules()
    if "api.index" in sys.modules:
        del sys.modules["api.index"]
    return importlib.import_module("api.index")


class TestAdminOrdersExportRoute:
    def test_route_registered(self, api_module):
        paths = {route.path for route in api_module.app.routes}
        assert "/api/admin/orders/export" in paths
        assert "/api/admin/orders/import" in paths

    def test_export_requires_admin(self, api_module):
        client = TestClient(api_module.app, raise_server_exceptions=True)
        response = client.get("/api/admin/orders/export")
        assert response.status_code == 401

    def test_import_requires_admin(self, api_module):
        client = TestClient(api_module.app, raise_server_exceptions=True)
        files = {"backup": ("orders.json", _minimal_backup_json(), "application/json")}
        response = client.post("/api/admin/orders/import", files=files)
        assert response.status_code == 401

    def test_export_returns_downloadable_json(self, api_module):
        from api.bootstrap import require_admin

        api_module.app.dependency_overrides[require_admin] = lambda: "admin@test.com"
        try:
            with (
                patch("api.routes.admin_orders_backup.export_orders_backup", new_callable=AsyncMock) as mock_export,
                patch("api.routes.admin_orders_backup.db.get_database", new_callable=AsyncMock) as mock_get_database,
            ):
                mock_get_database.return_value = object()
                mock_export.return_value = {"exported_at": "now", "generator": "test", "orders": [], "order_logs": []}
                client = TestClient(api_module.app, raise_server_exceptions=True)
                response = client.get("/api/admin/orders/export")
        finally:
            api_module.app.dependency_overrides.pop(require_admin, None)

        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        assert response.json()["generator"] == "test"

    def test_import_accepts_backup_and_returns_summary(self, api_module):
        from api.bootstrap import require_admin

        api_module.app.dependency_overrides[require_admin] = lambda: "admin@test.com"
        try:
            with (
                patch("api.routes.admin_orders_backup.restore_orders_backup", new_callable=AsyncMock) as mock_restore,
                patch("api.routes.admin_orders_backup.db.get_database", new_callable=AsyncMock) as mock_get_database,
            ):
                from src.services.order_backup_service import OrdersImportResult

                mock_get_database.return_value = object()
                mock_restore.return_value = OrdersImportResult(
                    orders_restored=1, orders_skipped=0, order_logs_restored=0, order_logs_skipped=0
                )
                client = TestClient(api_module.app, raise_server_exceptions=True)
                files = {"backup": ("orders.json", _minimal_backup_json(), "application/json")}
                response = client.post("/api/admin/orders/import", files=files)
        finally:
            api_module.app.dependency_overrides.pop(require_admin, None)

        assert response.status_code == 200
        body = response.json()
        assert body["orders_restored"] == 1

    def test_import_rejects_invalid_json_with_400(self, api_module):
        from api.bootstrap import require_admin

        api_module.app.dependency_overrides[require_admin] = lambda: "admin@test.com"
        try:
            client = TestClient(api_module.app, raise_server_exceptions=True)
            files = {"backup": ("orders.json", b"not json", "application/json")}
            response = client.post("/api/admin/orders/import", files=files)
        finally:
            api_module.app.dependency_overrides.pop(require_admin, None)

        assert response.status_code == 400

    def test_import_dry_run_does_not_restore(self, api_module):
        from api.bootstrap import require_admin

        api_module.app.dependency_overrides[require_admin] = lambda: "admin@test.com"
        try:
            with (
                patch("api.routes.admin_orders_backup.restore_orders_backup", new_callable=AsyncMock) as mock_restore,
                patch("api.routes.admin_orders_backup.db.get_database", new_callable=AsyncMock) as mock_get_database,
            ):
                mock_get_database.return_value = object()
                client = TestClient(api_module.app, raise_server_exceptions=True)
                files = {"backup": ("orders.json", _minimal_backup_json(), "application/json")}
                response = client.post("/api/admin/orders/import?dry_run=true", files=files)
        finally:
            api_module.app.dependency_overrides.pop(require_admin, None)

        assert response.status_code == 200
        mock_restore.assert_not_called()
        body = response.json()
        assert body["dry_run"] is True
        assert body["orders_to_restore"] == 1
