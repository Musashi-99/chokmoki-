"""Order creation (public) and the Razorpay payment webhook."""
from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from typing import Any, Dict, Optional
import json
from api.bootstrap import (
    EVENT_PAYMENT_CAPTURED,
    OrderCreateInput,
    OrderService,
    RazorpayService,
    ShiprocketService,
    get_client_ip,
    logger,
    publish_order_event,
    settings,
)
from api.json_utils import JSONEncoder

from src.security.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    IdempotencyService,
)

router = APIRouter()


@router.post("/api/orders/lookup")
async def api_lookup_orders(payload: Dict[str, Any]):
    """Public 'My Orders' lookup — returns a customer's own orders.

    Requires both email and phone (as entered at checkout) to match, so
    knowing someone's email alone isn't enough to see their order history.
    """
    if OrderService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    email = str(payload.get("email") or "").strip()
    phone = str(payload.get("phone") or "").strip()
    if not email or not phone:
        raise HTTPException(status_code=400, detail="Email and phone are required")

    service = OrderService()
    try:
        orders = await service.list_for_customer(email=email, phone=phone)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if logger:
            logger.error(f"Order lookup failed: {e}")
        raise HTTPException(status_code=500) from e

    body = json.loads(json.dumps(
        [o.model_dump(by_alias=True) for o in orders],
        cls=JSONEncoder,
    ))
    return JSONResponse(content={"data": body})


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


@router.post("/api/orders/initiate")
async def api_initiate_order(request: Request, payload: Dict[str, Any]):
    """Start a Razorpay (Checkout.js) order: reserve inventory, create the
    Razorpay order, store the pending order in Redis. Returns order_id
    immediately — the customer's order_id is known and screenshot-able
    before the payment modal even opens, same as the COD flow.
    """
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
            idem_fingerprint = idem_service.fingerprint(scope="order.initiate", payload=payload)
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
        payload.setdefault("paymentMethod", "razorpay")
        order_data = OrderCreateInput(**payload)
        service = OrderService()
        client_ip = get_client_ip(request) if get_client_ip else None
        result = await service.initiate_order(order_data, ip=client_ip)
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
            logger.error(f"Order initiation failed: {e}")
        raise HTTPException(status_code=500) from e

    response_body = json.loads(json.dumps(result.model_dump(), cls=JSONEncoder))
    if idem_storage_key and idem_fingerprint:
        await idem_service.store(
            idem_storage_key,
            idem_fingerprint,
            status_code=200,
            body=response_body,
        )
    return JSONResponse(content=response_body)


@router.post("/api/orders/verify")
async def api_verify_order_payment(payload: Dict[str, Any]):
    """Client-side Checkout.js success-callback fast path. NOT the source of
    truth — that's the webhook/stream path (see /webhook/razorpay below) —
    this just lets the customer see "confirmed" without waiting on the
    webhook round trip. Both converge on the same idempotent
    complete_pending_order(), so calling both is safe.
    """
    if OrderService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    order_id = payload.get("order_id") or payload.get("orderId")
    razorpay_order_id = payload.get("razorpay_order_id") or payload.get("razorpayOrderId")
    razorpay_payment_id = payload.get("razorpay_payment_id") or payload.get("razorpayPaymentId")
    razorpay_signature = payload.get("razorpay_signature") or payload.get("razorpaySignature")

    if not all([order_id, razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        raise HTTPException(status_code=400, detail="Missing required payment verification fields")

    try:
        service = OrderService()
        order = await service.verify_payment(
            order_id, razorpay_order_id, razorpay_payment_id, razorpay_signature
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if logger:
            logger.error(f"Payment verification failed for {order_id}: {e}")
        raise HTTPException(status_code=500) from e

    return JSONResponse(content=json.loads(json.dumps(
        order.model_dump(by_alias=True), cls=JSONEncoder
    )))


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
        
        # Both events carry a full payload.payment.entity with identical shape.
        # Not every Razorpay webhook config has "payment.captured" checked —
        # some only enable "order.paid"/"payment.authorized" — so both must
        # be treated as valid completion signals, or a real successful
        # payment can silently never complete our order (confirmed live: a
        # real test payment fired payment.authorized + order.paid but never
        # payment.captured, because that event type wasn't subscribed).
        if event in ("payment.captured", "order.paid"):
            payment_entity = payload_data.get("payment", {}).get("entity", {})

            razorpay_payment_id = payment_entity.get("id")
            razorpay_order_id = payment_entity.get("order_id")
            order_id = payment_entity.get("notes", {}).get("order_id")

            if not all([order_id, razorpay_order_id, razorpay_payment_id]):
                logger.warning(f"Incomplete webhook data (event={event}). Missing: order_id={order_id}, razorpay_order_id={razorpay_order_id}, razorpay_payment_id={razorpay_payment_id}")
                logger.debug(f"Full webhook payload: {webhook_data}")
                return JSONResponse(content={"status": "ignored", "reason": "incomplete_data"})

            # Durable, crash-safe processing: verify (above) is the only part
            # that must stay synchronous. The actual Mongo write happens in
            # src/orders/consumer.py via XREADGROUP — if this process crashes
            # between this XADD and the consumer acking it, XAUTOCLAIM
            # redelivers on restart (safe: complete_pending_order() is
            # idempotent). Razorpay only needs a fast 200 here.
            if publish_order_event is not None:
                await publish_order_event(
                    EVENT_PAYMENT_CAPTURED,
                    {
                        "order_id": order_id,
                        "razorpay_order_id": razorpay_order_id,
                        "razorpay_payment_id": razorpay_payment_id,
                    },
                )
            return JSONResponse(content={"status": "accepted", "order_id": order_id})

        if event == "payment.failed":
            failed_entity = payload_data.get("payment", {}).get("entity", {})
            logger.warning(
                f"Razorpay payment.failed for order_id="
                f"{failed_entity.get('notes', {}).get('order_id')}: "
                f"code={failed_entity.get('error_code')} "
                f"reason={failed_entity.get('error_reason')} "
                f"description={failed_entity.get('error_description')} "
                f"step={failed_entity.get('error_step')} "
                f"source={failed_entity.get('error_source')}"
            )
            return JSONResponse(content={"status": "ignored", "event": event})

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
