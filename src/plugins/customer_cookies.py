from __future__ import annotations

import secrets

from fastapi import Response

from src.config import settings
from src.models.user import CustomerAuthTokens
from src.plugins.customer_deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    REFRESH_COOKIE_PATH,
)

# Non-secret, JS-readable hint that a customer session cookie exists. The
# actual auth cookies are httponly, so the SPA has no way to tell "guest" from
# "logged in" without this — without it, every route fires a doomed
# /account/me on first paint for guests (401 + wasted RTT). Carries no
# session material, only used as a client-side skip signal.
SESSION_HINT_COOKIE = "chokmoki_customer_hint"


def set_customer_auth_cookies(response: Response, tokens: CustomerAuthTokens) -> None:
    secure = settings.cookie_secure
    samesite = settings.cookie_samesite
    domain = settings.admin_cookie_domain
    csrf_domain = settings.admin_csrf_cookie_domain or domain
    refresh_max_age = settings.customer_jwt_refresh_ttl_days * 24 * 60 * 60

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
        max_age=refresh_max_age,
        domain=domain,
        path=REFRESH_COOKIE_PATH,
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=secrets.token_urlsafe(32),
        httponly=False,
        secure=secure,
        samesite=samesite,
        max_age=refresh_max_age,
        domain=csrf_domain,
        path="/",
    )
    response.set_cookie(
        key=SESSION_HINT_COOKIE,
        value="1",
        httponly=False,
        secure=secure,
        samesite=samesite,
        max_age=refresh_max_age,
        domain=domain,
        path="/",
    )


def clear_customer_auth_cookies(response: Response) -> None:
    domain = settings.admin_cookie_domain
    csrf_domain = settings.admin_csrf_cookie_domain or domain
    response.delete_cookie(key=ACCESS_COOKIE, path="/", domain=domain)
    response.delete_cookie(key=REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, domain=domain)
    response.delete_cookie(key=CSRF_COOKIE, path="/", domain=csrf_domain)
    response.delete_cookie(key=SESSION_HINT_COOKIE, path="/", domain=domain)
