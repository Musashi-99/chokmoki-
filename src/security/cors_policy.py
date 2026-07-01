"""Strict CORS origin validation and middleware configuration."""

from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import urlparse

ALLOWED_CORS_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
ALLOWED_CORS_HEADERS = [
    "Accept",
    "Authorization",
    "Content-Type",
    "X-Request-Id",
    "X-Cron-Secret",
    # Admin SPA sends the CSRF token on cookie-authenticated requests; it must
    # survive cross-origin preflight or the whole admin panel breaks in prod.
    "X-CSRF-Token",
    # Storefront sends this on order creation (IDEMPOTENCY_REQUIRED_IN_PRODUCTION).
    "Idempotency-Key",
]
EXPOSED_CORS_HEADERS = ["X-Request-Id"]
CORS_MAX_AGE_SECONDS = 600


def normalize_origin(origin: str) -> str:
    """Normalize a single origin to scheme://host[:port] form."""
    value = (origin or "").strip()
    if not value:
        raise ValueError("CORS origin cannot be empty")
    if value == "*":
        return "*"

    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid CORS origin (missing scheme or host): {origin}")
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Invalid CORS origin scheme: {origin}")
    if parsed.username or parsed.password:
        raise ValueError(f"CORS origin must not include credentials: {origin}")
    if parsed.path not in {"", "/"}:
        raise ValueError(f"CORS origin must not include a path: {origin}")
    if parsed.query or parsed.fragment:
        raise ValueError(f"CORS origin must not include query or fragment: {origin}")

    host = parsed.hostname
    if not host:
        raise ValueError(f"Invalid CORS origin host: {origin}")

    port = parsed.port
    default_port = 443 if parsed.scheme == "https" else 80
    if port and port != default_port:
        return f"{parsed.scheme}://{host}:{port}"
    return f"{parsed.scheme}://{host}"


def parse_cors_origins(raw: str, *, allow_wildcard: bool = False) -> List[str]:
    """Parse comma-separated origins, normalize, and deduplicate."""
    text = (raw or "").strip()
    if not text:
        return []
    if text == "*":
        if not allow_wildcard:
            raise ValueError(
                "CORS wildcard (*) is not allowed; set explicit origins in CORS_ALLOWED_ORIGINS"
            )
        return ["*"]

    seen: set[str] = set()
    origins: List[str] = []
    for part in text.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        normalized = normalize_origin(candidate)
        if normalized not in seen:
            seen.add(normalized)
            origins.append(normalized)
    return origins


def build_cors_middleware_kwargs(origins: List[str]) -> Dict[str, Any]:
    """Build kwargs for Starlette CORSMiddleware with secure defaults."""
    if not origins:
        origins = ["http://localhost:5173"]

    allow_credentials = "*" not in origins
    return {
        "allow_origins": origins,
        "allow_credentials": allow_credentials,
        "allow_methods": ALLOWED_CORS_METHODS,
        "allow_headers": ALLOWED_CORS_HEADERS,
        "expose_headers": EXPOSED_CORS_HEADERS,
        "max_age": CORS_MAX_AGE_SECONDS,
    }
