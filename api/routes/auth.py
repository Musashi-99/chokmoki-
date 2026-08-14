"""Customer login (email + OTP via Brevo). Cookie
session auth, distinct from admin auth (api/routes/admin_auth.py) —
separate cookies, separate JWT `type` claims, separate Redis key prefixes.
"""
import re

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from typing import Optional

from src.plugins.customer_cookies import clear_customer_auth_cookies, set_customer_auth_cookies
from src.plugins.customer_deps import REFRESH_COOKIE
from src.services.customer_auth_service import CustomerAuthService

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_identifier(value: str) -> str:
    value = (value or "").strip()
    if _EMAIL_RE.match(value):
        return value.lower()
    raise ValueError("Enter a valid email address")


class OtpRequestPayload(BaseModel):
    identifier: str

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _validate_identifier(value)


class OtpVerifyPayload(BaseModel):
    identifier: str
    otp: str

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _validate_identifier(value)


@router.post("/api/auth/otp/request")
async def otp_request(payload: OtpRequestPayload):
    sent = await CustomerAuthService().request_otp(payload.identifier)
    if not sent:
        raise HTTPException(status_code=502, detail="Could not send OTP. Try again shortly.")
    return {"success": True}


@router.post("/api/auth/otp/verify")
async def otp_verify(payload: OtpVerifyPayload):
    result = await CustomerAuthService().verify_otp_and_login(payload.identifier, payload.otp)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired OTP")

    user, tokens = result
    response = JSONResponse(
        content={
            "user": {"id": user.id, "phone": user.phone, "name": user.name, "email": user.email},
            "expires_in": tokens.expires_in,
        }
    )
    set_customer_auth_cookies(response, tokens)
    return response


@router.post("/api/auth/refresh")
async def customer_refresh(
    refresh_cookie: Optional[str] = Cookie(None, alias=REFRESH_COOKIE),
):
    if not refresh_cookie:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    tokens = await CustomerAuthService().refresh(refresh_cookie)
    if not tokens:
        response = JSONResponse(status_code=401, content={"detail": "Invalid refresh token"})
        clear_customer_auth_cookies(response)
        return response

    response = JSONResponse(content={"expires_in": tokens.expires_in})
    set_customer_auth_cookies(response, tokens)
    return response


@router.post("/api/auth/logout")
async def customer_logout(
    request: Request,
    refresh_cookie: Optional[str] = Cookie(None, alias=REFRESH_COOKIE),
):
    principal = getattr(request.state, "customer_principal", None)
    auth_service = CustomerAuthService()

    if principal is None:
        from src.plugins.customer_deps import ACCESS_COOKIE

        access_cookie = request.cookies.get(ACCESS_COOKIE)
        if access_cookie:
            principal = await auth_service.verify_access_token(access_cookie)

    await auth_service.logout(principal, refresh_cookie)
    response = JSONResponse(content={"success": True})
    clear_customer_auth_cookies(response)
    return response
