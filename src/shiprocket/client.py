"""Raw Shiprocket API client — HTTP calls + auth token caching only.

No business logic here (order-to-payload mapping, courier selection, status
mapping) — see src/services/shiprocket_service.py for that. Base URL and
every endpoint path/shape below is taken directly from Shiprocket's own
cURL reference + Postman collection (docs/Shiprocket_API_cURL_Reference.md).
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from src.config import settings
from src.database.redis_connection import redis_client
from src.plugins.logger import logger

BASE_URL = "https://apiv2.shiprocket.in/v1/external"
TOKEN_CACHE_KEY = "shiprocket:token"
# Shiprocket doesn't document a token TTL. Cache with a conservative soft
# TTL for proactive refresh, and ALSO transparently re-login-and-retry-once
# on any 401 (see _request) so this self-heals regardless of the real,
# undocumented expiry.
TOKEN_SOFT_TTL_SECONDS = 9 * 24 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 20.0


class ShiprocketAPIError(Exception):
    """Raised on any non-recoverable Shiprocket API failure."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class ShiprocketNotConfiguredError(ShiprocketAPIError):
    """Raised when the feature is disabled or missing required config — a
    client-actionable setup problem, distinct from an upstream API failure.
    Routes should map this to 400, not 502, so the message isn't redacted
    by the generic 5xx sanitizer in src/security/error_handling.py.
    """


class ShiprocketClient:
    async def _login(self) -> str:
        if not settings.shiprocket_email or not settings.shiprocket_password:
            raise ShiprocketAPIError("Shiprocket credentials are not configured")
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                "/auth/login",
                json={"email": settings.shiprocket_email, "password": settings.shiprocket_password},
            )
        if resp.status_code != 200:
            # Never log settings.shiprocket_password — only status/body, which
            # Shiprocket's own error responses don't echo credentials in.
            if logger:
                logger.error(f"Shiprocket login failed: {resp.status_code} {resp.text[:300]}")
            raise ShiprocketAPIError(
                f"Shiprocket login failed: {resp.status_code}",
                status_code=resp.status_code,
                payload=self._safe_json(resp),
            )
        token = (self._safe_json(resp) or {}).get("token")
        if not token:
            if logger:
                logger.error("Shiprocket login response missing token")
            raise ShiprocketAPIError("Shiprocket login response missing token")
        redis = await redis_client.get_client()
        await redis.set(TOKEN_CACHE_KEY, token, ex=TOKEN_SOFT_TTL_SECONDS)
        return token

    async def _get_token(self, *, force_refresh: bool = False) -> str:
        if not force_refresh:
            redis = await redis_client.get_client()
            cached = await redis.get(TOKEN_CACHE_KEY)
            if cached:
                return cached
        return await self._login()

    @staticmethod
    def _safe_json(resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Any:
        token = await self._get_token()
        resp: Optional[httpx.Response] = None

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=REQUEST_TIMEOUT_SECONDS) as client:
            for attempt in range(2):
                headers = {"Authorization": f"Bearer {token}"}
                resp = await client.request(method, path, json=json, params=params, headers=headers)
                if resp.status_code == 401 and attempt == 0:
                    token = await self._get_token(force_refresh=True)
                    continue
                if resp.status_code == 429 and attempt == 0:
                    await asyncio.sleep(2)
                    continue
                break

        if resp is None:
            raise ShiprocketAPIError("Shiprocket request produced no response")

        if resp.status_code >= 400:
            if logger:
                logger.error(
                    f"Shiprocket API error {method} {path}: {resp.status_code} {resp.text[:500]}"
                )
            raise ShiprocketAPIError(
                f"Shiprocket API error: {resp.status_code}",
                status_code=resp.status_code,
                payload=self._safe_json(resp),
            )
        return self._safe_json(resp)

    # ---- endpoints ----

    async def create_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/orders/create/adhoc", json=payload)

    async def check_serviceability(
        self, *, pickup_postcode: str, delivery_postcode: str, weight: float, cod: bool
    ) -> List[Dict[str, Any]]:
        params = {
            "pickup_postcode": pickup_postcode,
            "delivery_postcode": delivery_postcode,
            "weight": weight,
            "cod": 1 if cod else 0,
        }
        data = await self._request("GET", "/courier/serviceability/", params=params)
        return ((data or {}).get("data") or {}).get("available_courier_companies") or []

    async def assign_awb(self, *, shipment_id: int, courier_id: Optional[int] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"shipment_id": shipment_id}
        if courier_id is not None:
            payload["courier_id"] = courier_id
        return await self._request("POST", "/courier/assign/awb", json=payload)

    async def generate_pickup(self, *, shipment_id: int) -> Dict[str, Any]:
        return await self._request("POST", "/courier/generate/pickup", json={"shipment_id": [shipment_id]})

    async def generate_label(self, *, shipment_id: int) -> Dict[str, Any]:
        return await self._request("POST", "/courier/generate/label", json={"shipment_id": [shipment_id]})

    async def generate_invoice(self, *, order_id: int) -> Dict[str, Any]:
        return await self._request("POST", "/orders/print/invoice", json={"ids": [order_id]})

    async def track_by_awb(self, *, awb_code: str) -> Dict[str, Any]:
        return await self._request("GET", f"/courier/track/awb/{awb_code}")

    async def cancel_order(self, *, order_id: int) -> Dict[str, Any]:
        return await self._request("POST", "/orders/cancel", json={"ids": [order_id]})

    async def cancel_shipment(self, *, awb_code: str) -> Dict[str, Any]:
        return await self._request("POST", "/orders/cancel/shipment/awbs", json={"awbs": [awb_code]})
