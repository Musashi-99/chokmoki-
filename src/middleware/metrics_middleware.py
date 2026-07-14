"""HTTP request count/latency metrics — the only observability this app had
before was 2 fraud-specific metrics; this is the general request-path
counterpart, feeding the same Prometheus /metrics endpoint.
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.plugins.metrics import HTTP_REQUESTS_TOTAL, HTTP_REQUEST_LATENCY_MS


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        # request.scope["route"] is set by Starlette's routing by the time
        # call_next returns — use its templated path ("/api/orders/{order_id}")
        # rather than request.url.path, which would give every distinct
        # order_id its own Prometheus label (unbounded cardinality).
        route = request.scope.get("route")
        path = getattr(route, "path", None) or request.url.path
        HTTP_REQUESTS_TOTAL.labels(
            method=request.method, path=path, status_code=response.status_code
        ).inc()
        HTTP_REQUEST_LATENCY_MS.labels(method=request.method, path=path).observe(
            (time.monotonic() - start) * 1000
        )
        return response
