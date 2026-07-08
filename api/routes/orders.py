"""Order creation (public) and the Razorpay payment webhook."""
from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from typing import Any, Dict, Optional
import json
from api.bootstrap import (
    OrderCreateInput,
    OrderService,
    RazorpayService,
    ShiprocketService,
    get_client_ip,
    logger,
    settings,
)
from api.json_utils import JSONEncoder

from src.security.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    IdempotencyService,
)

router = APIRouter()


@router.post("/api/orders")
async def api_create_order(request: Request, payload: Dict[str, Any]):
    """Create a new order (public endpoint)."""
    if OrderService is None or OrderCreateInput is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    idem_key = request.headers.get("Idempotency-Key") or payload.get("idempotencyKey")
    if (
        settings
        and settings.is_production
        and settings.idempotency_required_in_production
        and not idem_key
    ):
        raise HTTPException(status_code=400, detail="Idempotency-Key is required")

    idem_service = IdempotencyService()
    idem_storage_key = None
    idem_fingerprint = None
    if idem_key:
        try:
            idem_storage_key = idem_service.normalize_key(idem_key)
            idem_fingerprint = idem_service.fingerprint(scope="order.create", payload=payload)
            cached = await idem_service.begin(idem_storage_key, idem_fingerprint)
            if cached:
                return JSONResponse(status_code=cached.status_code, content=cached.body)
        except IdempotencyConflictError:
            raise HTTPException(status_code=409, detail="Idempotency-Key reused with different payload")
        except IdempotencyInProgressError:
            raise HTTPException(
                status_code=409,
                detail="A request with this Idempotency-Key is already being processed",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        order_data = OrderCreateInput(**payload)
        service = OrderService()
        client_ip = get_client_ip(request) if get_client_ip else None
        order = await service.create(order_data, ip=client_ip)
    except HTTPException:
        if idem_storage_key:
            await idem_service.release_lock(idem_storage_key)
        raise
    except ValueError as e:
        if idem_storage_key:
            await idem_service.release_lock(idem_storage_key)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if idem_storage_key:
            await idem_service.release_lock(idem_storage_key)
        if logger:
            logger.error(f"Order creation failed: {e}")
        raise HTTPException(status_code=500) from e

    response_body = json.loads(json.dumps(
        order.model_dump(by_alias=True),
        cls=JSONEncoder
    ))
    if idem_storage_key and idem_fingerprint:
        await idem_service.store(
            idem_storage_key,
            idem_fingerprint,
            status_code=200,
            body=response_body,
        )
    return JSONResponse(content=response_body)

@router.post("/webhook/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature")
):
    """Razorpay webhook endpoint with HMAC verification"""
    if RazorpayService is None or OrderService is None:
        raise HTTPException(status_code=500, detail="Services not initialized")
    
    try:
        body = await request.body()
        payload = body.decode('utf-8')
        
        if not x_razorpay_signature:
            logger.warning("Webhook request missing X-Razorpay-Signature header")
            raise HTTPException(status_code=400, detail="Missing X-Razorpay-Signature header")
        
        if not settings or not settings.razorpay_webhook_secret:
            logger.error(
                "RAZORPAY_WEBHOOK_SECRET is not set in environment variables. "
                "If you configured a webhook secret in Razorpay Dashboard, you must set RAZORPAY_WEBHOOK_SECRET in your .env file."
            )
            raise HTTPException(
                status_code=500, 
                detail="Webhook secret not configured. Please set RAZORPAY_WEBHOOK_SECRET in your environment variables."
            )
        
        razorpay_service = RazorpayService()
        if not razorpay_service.verify_webhook_signature(payload, x_razorpay_signature):
            logger.error(
                f"Webhook signature verification failed. "
                f"Make sure RAZORPAY_WEBHOOK_SECRET matches the secret set in Razorpay Dashboard. "
                f"Signature received: {x_razorpay_signature[:30]}..."
            )
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
        
        webhook_data = json.loads(payload)
        event = webhook_data.get("event")
        payload_data = webhook_data.get("payload", {})
        
        if event == "payment.captured":
            payment_entity = payload_data.get("payment", {}).get("entity", {})
            
            razorpay_payment_id = payment_entity.get("id")
            razorpay_order_id = payment_entity.get("order_id")
            order_id = payment_entity.get("notes", {}).get("order_id")
            
            if not all([order_id, razorpay_order_id, razorpay_payment_id]):
                logger.warning(f"Incomplete webhook data. Missing: order_id={order_id}, razorpay_order_id={razorpay_order_id}, razorpay_payment_id={razorpay_payment_id}")
                logger.debug(f"Full webhook payload: {webhook_data}")
                return JSONResponse(content={"status": "ignored", "reason": "incomplete_data"})
            
            order_service = OrderService()
            try:
                _order, completion_status = await order_service.complete_pending_order(
                    order_id, razorpay_order_id, razorpay_payment_id
                )
                if completion_status == "not_found":
                    logger.warning(
                        f"Order {order_id} not found in Redis, may already be processed"
                    )
                    return JSONResponse(
                        content={"status": "ignored", "reason": "order_not_found"}
                    )
                message = (
                    "already_processed"
                    if completion_status == "existing"
                    else "created"
                )
                return JSONResponse(
                    content={
                        "status": "success",
                        "order_id": order_id,
                        "message": message,
                    }
                )
            except Exception as e:
                logger.error(f"Failed to process webhook for order {order_id}: {e}")
                raise HTTPException(
                    status_code=500,
                )
        
        logger.info(f"Webhook event {event} received but not processed")
        return JSONResponse(content={"status": "ignored", "event": event})
    
    except HTTPException:
        raise
    except Exception as e:
        if logger:
            logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


@router.get("/webhook/courier-updates")
async def shiprocket_webhook_probe(request: Request):
    """Some webhook dashboards (Shiprocket's included, unconfirmed) do a GET
    reachability check against the URL before letting you save it. The real
    delivery is always POST; this just avoids a 405 breaking that check.
    """
    if logger:
        logger.info(
            f"Shiprocket webhook GET probe from {request.client.host if request.client else 'unknown'}"
        )
    return JSONResponse(content={"status": "ok"})


@router.post("/webhook/courier-updates")
async def shiprocket_webhook(request: Request, x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    """Shiprocket shipment status webhook.

    Per Shiprocket's own docs this URL "should respond with only code 200"
    regardless of outcome (their retry/delivery system treats anything else
    as a delivery failure) — so auth failures and processing errors are
    logged, never surfaced as a non-200 status. Everything here is logged
    verbosely (headers, raw body, outcome) since this is the only vantage
    point to debug delivery issues from Shiprocket's side.
    """
    client_host = request.client.host if request.client else "unknown"
    raw_body = await request.body()

    if logger:
        logger.info(
            f"Shiprocket webhook POST received from {client_host} | "
            f"content-length={len(raw_body)} | "
            f"x-api-key present={bool(x_api_key)} len={len(x_api_key) if x_api_key else 0}"
        )
        logger.debug(f"Shiprocket webhook raw body: {raw_body[:4000]!r}")

    if ShiprocketService is None:
        if logger:
            logger.warning("Shiprocket webhook: ShiprocketService not available (not initialized)")
        return JSONResponse(content={"status": "ignored"})

    try:
        service = ShiprocketService()
    except Exception as e:
        if logger:
            logger.warning(f"Shiprocket webhook: service init failed (likely disabled/misconfigured): {e}")
        return JSONResponse(content={"status": "ignored"})

    if not service.verify_webhook_token(x_api_key):
        if logger:
            logger.warning(
                f"Shiprocket webhook rejected: invalid or missing x-api-key from {client_host} "
                f"(received len={len(x_api_key) if x_api_key else 0})"
            )
        return JSONResponse(content={"status": "ok"})

    try:
        import json as _json
        body = _json.loads(raw_body)
    except Exception as e:
        if logger:
            logger.warning(f"Shiprocket webhook: invalid JSON body from {client_host}: {e}")
        return JSONResponse(content={"status": "ok"})

    if logger:
        logger.info(
            f"Shiprocket webhook payload | order_id={body.get('order_id')} "
            f"current_status={body.get('current_status') or body.get('shipment_status')} "
            f"awb={body.get('awb')} scans_count={len(body.get('scans') or [])}"
        )

    try:
        await service.handle_webhook(body)
        if logger:
            logger.info(f"Shiprocket webhook processed successfully for order_id={body.get('order_id')}")
    except Exception as e:
        if logger:
            logger.exception(f"Shiprocket webhook processing error for order_id={body.get('order_id')}: {e}")

    return JSONResponse(content={"status": "ok"})
