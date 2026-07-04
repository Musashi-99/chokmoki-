"""Order creation (public) and the Razorpay payment webhook."""
from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from typing import Any, Dict, Optional
import json
from api.bootstrap import OrderCreateInput, OrderService, RazorpayService, logger, settings
from api.json_utils import JSONEncoder

from src.security.idempotency import IdempotencyConflictError, IdempotencyService

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
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        order_data = OrderCreateInput(**payload)
        service = OrderService()
        order = await service.create(order_data)
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
