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
    # CSRF cookie needs its own (usually wider) domain — see config.py for why.
    csrf_domain = settings.admin_csrf_cookie_domain or domain

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
        domain=csrf_domain,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    domain = settings.admin_cookie_domain
    csrf_domain = settings.admin_csrf_cookie_domain or domain
    for key, path, cookie_domain in (
        (ACCESS_COOKIE, "/", domain),
        (REFRESH_COOKIE, REFRESH_COOKIE_PATH, domain),
        (CSRF_COOKIE, "/", csrf_domain),
    ):
        response.delete_cookie(key=key, path=path, domain=cookie_domain)
