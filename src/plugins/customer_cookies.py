from __future__ import annotations

from fastapi import Response

from src.config import settings
from src.models.user import CustomerAuthTokens
from src.plugins.customer_deps import ACCESS_COOKIE, REFRESH_COOKIE, REFRESH_COOKIE_PATH


def set_customer_auth_cookies(response: Response, tokens: CustomerAuthTokens) -> None:
    secure = settings.cookie_secure
    samesite = settings.cookie_samesite
    domain = settings.admin_cookie_domain  # same storefront-domain config as admin cookies

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
        max_age=settings.customer_jwt_refresh_ttl_days * 24 * 60 * 60,
        domain=domain,
        path=REFRESH_COOKIE_PATH,
    )


def clear_customer_auth_cookies(response: Response) -> None:
    domain = settings.admin_cookie_domain
    response.delete_cookie(key=ACCESS_COOKIE, path="/", domain=domain)
    response.delete_cookie(key=REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, domain=domain)
