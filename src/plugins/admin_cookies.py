from __future__ import annotations

from typing import Optional

from fastapi import Response

from src.config import settings
from src.models.admin_auth import AuthTokens
from src.plugins.admin_deps import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE

REFRESH_COOKIE_PATH = "/api/admin"


def set_auth_cookies(response: Response, tokens: AuthTokens) -> None:
    secure = settings.cookie_secure
    samesite = settings.cookie_samesite
    domain = settings.admin_cookie_domain

    response.set_cookie(
        key=ACCESS_COOKIE,
        value=tokens.access_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=tokens.expires_in,
        domain=domain,
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=tokens.refresh_token,
        httponly=True,
        secure=secure,
        samesite="strict" if samesite != "none" else "none",
        max_age=settings.jwt_refresh_ttl_days * 24 * 60 * 60,
        domain=domain,
        path=REFRESH_COOKIE_PATH,
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=tokens.csrf_token,
        httponly=False,
        secure=secure,
        samesite=samesite,
        max_age=settings.jwt_refresh_ttl_days * 24 * 60 * 60,
        domain=domain,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    domain = settings.admin_cookie_domain
    for key, path in (
        (ACCESS_COOKIE, "/"),
        (REFRESH_COOKIE, REFRESH_COOKIE_PATH),
        (CSRF_COOKIE, "/"),
    ):
        response.delete_cookie(key=key, path=path, domain=domain)
