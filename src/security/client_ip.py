"""Trusted client IP extraction — resists X-Forwarded-For spoofing."""

from __future__ import annotations

import ipaddress
import os
from typing import Optional, Sequence

from starlette.requests import Request

from src.config import settings

VERCEL_FORWARDED_HEADER = "x-vercel-forwarded-for"
REAL_IP_HEADER = "x-real-ip"
FORWARDED_FOR_HEADER = "x-forwarded-for"


def _first_valid_ip(value: str) -> Optional[str]:
    for part in value.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        return candidate
    return None


def _header_value(request: Request, name: str) -> Optional[str]:
    return request.headers.get(name) or request.headers.get(name.lower())


def _is_vercel_deployment() -> bool:
    return os.environ.get("VERCEL") == "1"


def extract_client_ip(
    request: Request,
    *,
    trusted_proxy_enabled: Optional[bool] = None,
    trust_x_forwarded_for: Optional[bool] = None,
    custom_header: Optional[str] = None,
) -> str:
    trusted_proxy = (
        settings.trusted_proxy_enabled
        if trusted_proxy_enabled is None
        else trusted_proxy_enabled
    )
    allow_xff = (
        settings.trust_x_forwarded_for
        if trust_x_forwarded_for is None
        else trust_x_forwarded_for
    )
    override_header = custom_header or settings.rate_limit_ip_header

    if override_header:
        header_value = _header_value(request, override_header)
        if header_value:
            parsed = _first_valid_ip(header_value)
            if parsed:
                return parsed

    if _is_vercel_deployment():
        vercel_ip = _header_value(request, VERCEL_FORWARDED_HEADER)
        if vercel_ip:
            parsed = _first_valid_ip(vercel_ip)
            if parsed:
                return parsed

    if trusted_proxy:
        real_ip = _header_value(request, REAL_IP_HEADER)
        if real_ip:
            parsed = _first_valid_ip(real_ip)
            if parsed:
                return parsed

        if allow_xff:
            forwarded = _header_value(request, FORWARDED_FOR_HEADER)
            if forwarded:
                parsed = _first_valid_ip(forwarded)
                if parsed:
                    return parsed

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def get_client_ip(request: Request) -> str:
    return extract_client_ip(request)


AUTH_SENSITIVE_PATHS: Sequence[str] = (
    "/api/admin/login",
    "/api/admin/refresh",
    "/api/admin/logout",
)


def is_auth_sensitive_path(path: str) -> bool:
    return path in AUTH_SENSITIVE_PATHS


def should_fail_closed_for_path(path: str) -> bool:
    if is_auth_sensitive_path(path):
        return settings.rate_limit_auth_fail_closed
    return settings.rate_limit_fail_closed
