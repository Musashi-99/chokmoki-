from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request

from src.config import settings
from src.models.user import CustomerPrincipal
from src.services.customer_auth_service import CustomerAuthService

ACCESS_COOKIE = "chokmoki_customer_access"
REFRESH_COOKIE = "chokmoki_customer_refresh"
REFRESH_COOKIE_PATH = "/api/auth"
CSRF_COOKIE = "chokmoki_customer_csrf"
CSRF_HEADER = "X-CSRF-Token"


async def resolve_customer_principal(
    request: Request,
    access_cookie: Optional[str] = Cookie(None, alias=ACCESS_COOKIE),
) -> CustomerPrincipal:
    if not access_cookie:
        raise HTTPException(status_code=401, detail="Missing customer credentials")

    principal = await CustomerAuthService().verify_access_token(access_cookie)
    if not principal:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    request.state.customer_principal = principal
    return principal


async def enforce_customer_csrf(request: Request) -> None:
    if not settings.csrf_enabled:
        return
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return

    csrf_cookie = request.cookies.get(CSRF_COOKIE)
    csrf_header = request.headers.get(CSRF_HEADER)
    if not csrf_cookie or not csrf_header:
        raise HTTPException(status_code=403, detail="CSRF token required")
    if not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


async def require_customer_auth(
    request: Request,
    principal: CustomerPrincipal = Depends(resolve_customer_principal),
) -> CustomerPrincipal:
    await enforce_customer_csrf(request)
    return principal


async def resolve_customer_principal_optional(
    request: Request,
    access_cookie: Optional[str] = Cookie(None, alias=ACCESS_COOKIE),
) -> Optional[CustomerPrincipal]:
    """Never raises — returns None for guests/missing/expired sessions.
    Used by endpoints (checkout) that must keep working anonymously but
    should still link the order to an account when one is logged in.
    """
    if not access_cookie:
        return None
    principal = await CustomerAuthService().verify_access_token(access_cookie)
    if principal:
        request.state.customer_principal = principal
    return principal
