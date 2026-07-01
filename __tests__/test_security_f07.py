"""F-07 CORS wildcard removal and strict origin allowlist tests."""

from __future__ import annotations

import importlib
import json
import os
import sys
import types
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError

from src.config import INSECURE_DEFAULTS, Settings
from src.security.cors_policy import (
    ALLOWED_CORS_HEADERS,
    ALLOWED_CORS_METHODS,
    build_cors_middleware_kwargs,
    normalize_origin,
    parse_cors_origins,
)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


class TestVercelConfig:
    def test_vercel_json_has_no_wildcard_cors_headers(self):
        path = os.path.join(ROOT, "vercel.json")
        with open(path, encoding="utf-8") as handle:
            config = json.load(handle)
        headers = config.get("headers", [])
        for block in headers:
            for header in block.get("headers", []):
                key = header.get("key", "").lower()
                value = header.get("value", "")
                assert key != "access-control-allow-origin"
                assert value != "*"


class TestOriginValidation:
    def test_normalize_strips_trailing_slash(self):
        assert normalize_origin("https://shop.example.com/") == "https://shop.example.com"

    def test_normalize_preserves_non_default_port(self):
        assert normalize_origin("http://localhost:5173") == "http://localhost:5173"

    def test_rejects_path_in_origin(self):
        with pytest.raises(ValueError, match="path"):
            normalize_origin("https://shop.example.com/admin")

    def test_rejects_invalid_scheme(self):
        with pytest.raises(ValueError, match="scheme"):
            normalize_origin("ftp://shop.example.com")

    def test_parse_deduplicates_origins(self):
        raw = "https://a.example.com,https://a.example.com/,https://b.example.com"
        assert parse_cors_origins(raw) == [
            "https://a.example.com",
            "https://b.example.com",
        ]

    def test_wildcard_blocked_when_not_allowed(self):
        with pytest.raises(ValueError, match="wildcard"):
            parse_cors_origins("*", allow_wildcard=False)

    def test_wildcard_allowed_in_development_mode(self):
        assert parse_cors_origins("*", allow_wildcard=True) == ["*"]


class TestCorsMiddlewareKwargs:
    def test_explicit_origins_enable_credentials(self):
        kwargs = build_cors_middleware_kwargs(["https://shop.example.com"])
        assert kwargs["allow_credentials"] is True
        assert kwargs["allow_methods"] == ALLOWED_CORS_METHODS
        assert kwargs["allow_headers"] == ALLOWED_CORS_HEADERS

    def test_wildcard_disables_credentials(self):
        kwargs = build_cors_middleware_kwargs(["*"])
        assert kwargs["allow_credentials"] is False

    def test_csrf_header_is_allowed(self):
        # The admin SPA attaches X-CSRF-Token to every authenticated request
        # once the CSRF cookie exists. It must survive cross-origin preflight.
        assert "X-CSRF-Token" in ALLOWED_CORS_HEADERS


class TestSettingsCorsGuard:
    def test_production_rejects_wildcard_cors(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("ADMIN_PASSWORD", INSECURE_DEFAULTS["admin_password"])
        monkeypatch.setenv("JWT_SECRET", INSECURE_DEFAULTS["jwt_secret"])
        monkeypatch.setenv("CRON_SECRET", "short")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

        with pytest.raises(ValueError):
            Settings()

    def test_development_rejects_malformed_origin(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "not-a-valid-origin")

        with pytest.raises(ValueError, match="Invalid CORS origin"):
            Settings()


class TestCorsIntegration:
    @pytest.fixture
    def cors_client(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:5173,https://shop.example.com",
        )

        _stub_external_modules()

        import src.config as config_module

        if "api.index" in sys.modules:
            del sys.modules["api.index"]
        importlib.reload(config_module)
        api_module = importlib.import_module("api.index")

        with patch(
            "src.plugins.rate_limit.redis_client.get_client",
            new_callable=AsyncMock,
        ), patch.object(
            api_module, "ProductService", create=True
        ):
            yield TestClient(api_module.app)

    def test_allowed_origin_receives_cors_headers(self, cors_client):
        response = cors_client.options(
            "/api/products",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:5173"
        )

    def test_disallowed_origin_omits_cors_headers(self, cors_client):
        response = cors_client.options(
            "/api/products",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 400
        assert response.headers.get("access-control-allow-origin") is None

    def test_preflight_allows_admin_csrf_header(self, cors_client):
        # Reproduces the production admin-login breakage: the SPA sends
        # X-CSRF-Token on authenticated requests to the cross-origin API,
        # so the preflight must not be rejected.
        response = cors_client.options(
            "/api/admin/me",
            headers={
                "Origin": "https://shop.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-CSRF-Token, Content-Type",
            },
        )
        assert response.status_code == 200
        allowed = response.headers.get("access-control-allow-headers", "").lower()
        assert "x-csrf-token" in allowed

    def test_preflight_includes_restricted_methods(self, cors_client):
        response = cors_client.options(
            "/api/products",
            headers={
                "Origin": "https://shop.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        methods = response.headers.get("access-control-allow-methods", "")
        assert "POST" in methods
        assert "GET" in methods
