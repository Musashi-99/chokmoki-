"""Scheduled maintenance jobs, authenticated via X-Cron-Secret."""
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from api.bootstrap import OrderService, logger, settings

router = APIRouter()


def require_cron_secret(x_cron_secret: Optional[str] = Header(None, alias="X-Cron-Secret")) -> None:
    if settings is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    expected = settings.cron_secret
    if settings.is_production:
        if not expected:
            raise HTTPException(status_code=500, detail="CRON_SECRET is not configured")
        if not x_cron_secret or not secrets.compare_digest(x_cron_secret, expected):
            raise HTTPException(status_code=401, detail="Unauthorized")
    elif expected:
        if not x_cron_secret or not secrets.compare_digest(x_cron_secret, expected):
            raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/cron/inventory/reconcile", dependencies=[Depends(require_cron_secret)])
async def inventory_reconcile_cron():
    """Release inventory reservations for orders nearing Redis TTL expiry."""
    try:
        from src.services.inventory_service import InventoryService

        released = await InventoryService().reconcile_stale_reservations()
        return JSONResponse(content={"released": released})
    except HTTPException:
        raise
    except Exception as e:
        if logger:
            logger.error(f"Inventory reconcile cron error: {e}")
        raise HTTPException(status_code=500) from e


@router.post("/cron/orders/reconcile", dependencies=[Depends(require_cron_secret)])
async def orders_reconcile_cron():
    """F-13: recover paid Razorpay orders whose webhook was lost or unverified.

    Queries Razorpay for captured payments on pending orders and persists them,
    so a missing/misconfigured RAZORPAY_WEBHOOK_SECRET (or a dropped webhook)
    cannot silently lose paid orders before their Redis TTL expires.
    """
    if OrderService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        summary = await OrderService().reconcile_pending_payments()
        return JSONResponse(content=summary)
    except HTTPException:
        raise
    except Exception as e:
        if logger:
            logger.error(f"Orders reconcile cron error: {e}")
        raise HTTPException(status_code=500) from e
