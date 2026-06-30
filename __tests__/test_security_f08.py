"""F-08 generic client errors and correlation ID tests."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.error_handling import (
    CORRELATION_ID_HEADER,
    error_response,
    new_correlation_id,
    register_exception_handlers,
    resolve_correlation_id,
    sanitize_client_detail,
)


def _make_request(headers: dict | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/test",
        "headers": [
            (key.lower().encode(), value.encode())
            for key, value in (headers or {}).items()
        ],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    return Request(scope)


class TestSanitizeClientDetail:
    def test_internal_500_always_generic(self):
        detail = sanitize_client_detail(
            "pymongo.errors.ServerSelectionTimeoutError: connection refused",
            500,
        )
        assert detail == "An internal error occurred."

    def test_mongo_error_on_400_is_generic(self):
        detail = sanitize_client_detail(
            "E11000 duplicate key error collection: orders",
            400,
        )
        assert detail == "The request could not be processed."

    def test_safe_business_message_preserved(self):
        detail = sanitize_client_detail("Order not found", 404)
        assert detail == "Order not found"

    def test_auth_messages_preserved(self):
        detail = sanitize_client_detail("Invalid email or password", 401)
        assert detail == "Invalid email or password"


class TestCorrelationId:
    def test_generates_when_missing(self):
        request = _make_request()
        correlation_id = resolve_correlation_id(request)
        assert len(correlation_id) == 32

    def test_reuses_incoming_header(self):
        request = _make_request({CORRELATION_ID_HEADER: "abc123deadbeef"})
        assert resolve_correlation_id(request) == "abc123deadbeef"

    def test_error_response_includes_correlation_id(self):
        correlation_id = new_correlation_id()
        response = error_response(500, correlation_id)
        payload = response.body.decode()
        assert correlation_id in payload
        assert response.headers[CORRELATION_ID_HEADER] == correlation_id


class TestExceptionHandlers:
    @pytest.fixture
    def handler_client(self):
        import logging

        from fastapi import FastAPI

        from src.middleware.correlation_id import CorrelationIdMiddleware

        app = FastAPI()
        register_exception_handlers(app, logging.getLogger("test_security_f08"))
        app.add_middleware(CorrelationIdMiddleware)

        @app.get("/not-found")
        async def not_found():
            raise HTTPException(status_code=404, detail="Order not found")

        @app.get("/boom")
        async def boom():
            raise RuntimeError("pymongo internal failure at file.py line 99")

        return TestClient(app, raise_server_exceptions=False)

    def test_http_exception_returns_correlation_id(self, handler_client):
        response = handler_client.get(
            "/not-found",
            headers={CORRELATION_ID_HEADER: "test-correlation-001"},
        )
        assert response.status_code == 404
        body = response.json()
        assert body["correlation_id"] == "test-correlation-001"
        assert body["detail"] == "Order not found"
        assert response.headers[CORRELATION_ID_HEADER] == "test-correlation-001"

    def test_internal_error_is_generic(self, handler_client):
        response = handler_client.get("/boom")
        assert response.status_code == 500
        body = response.json()
        assert body["detail"] == "An internal error occurred."
        assert "correlation_id" in body
        assert "pymongo" not in body["detail"]


class TestCqrsValidationErrors:
    @pytest.mark.asyncio
    async def test_invalid_params_return_generic_message(self):
        from src.cqrs.router import CQRSRouter

        with pytest.raises(ValueError, match="Invalid request parameters"):
            CQRSRouter._validate_params(
                "order.list",
                {"userEmail": {"$gt": ""}},
            )
