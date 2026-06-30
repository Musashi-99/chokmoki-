"""Attach a correlation ID to every request and response."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.security.error_handling import CORRELATION_ID_HEADER, resolve_correlation_id


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = resolve_correlation_id(request)
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        if CORRELATION_ID_HEADER not in response.headers:
            response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
