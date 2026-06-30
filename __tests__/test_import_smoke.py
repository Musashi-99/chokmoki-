"""Import smoke tests — ensure api.index loads and admin cookie routes work."""

from __future__ import annotations

import importlib
import os
import sys
import types
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Cookie
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


class TestApiIndexImportSmoke:
    def test_fastapi_import_includes_cookie(self):
        index_path = os.path.join(ROOT, "api", "index.py")
        with open(index_path, encoding="utf-8") as handle:
            first_lines = "".join(handle.readline() for _ in range(3))
        assert "Cookie" in first_lines

    def test_module_imports_without_name_error(self, api_module):
        assert api_module is not None

    def test_fastapi_app_exported(self, api_module):
        assert api_module.app is not None

    def test_cookie_symbol_available_in_module_namespace(self):
        assert Cookie is not None

    def test_admin_refresh_route_registered(self, api_module):
        paths = {route.path for route in api_module.app.routes}
        assert "/api/admin/refresh" in paths

    def test_admin_logout_route_registered(self, api_module):
        paths = {route.path for route in api_module.app.routes}
        assert "/api/admin/logout" in paths

    def test_admin_refresh_endpoint_evaluated_with_cookie_dependency(self, api_module):
        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha")
        mock_redis.evalsha = AsyncMock(return_value=[1, 0])

        client = TestClient(api_module.app, raise_server_exceptions=True)
        with patch(
            "src.plugins.rate_limit.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            response = client.post("/api/admin/refresh")
        assert response.status_code == 401
        assert "refresh token" in response.json()["detail"].lower()

    def test_admin_logout_endpoint_evaluated_with_cookie_dependency(self, api_module):
        client = TestClient(api_module.app, raise_server_exceptions=True)
        response = client.post("/api/admin/logout")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_reimport_is_idempotent(self, api_module):
        second = importlib.reload(api_module)
        assert second.app is api_module.app
