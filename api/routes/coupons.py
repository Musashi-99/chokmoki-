from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Any, Dict
from pydantic import ValidationError
from api.bootstrap import CouponPreviewInput, DiscountService, ProductService
from api.json_utils import JSONEncoder
import json

router = APIRouter()


@router.post("/api/coupons/preview")
async def preview_coupon(payload: Dict[str, Any]):
    if DiscountService is None or ProductService is None or CouponPreviewInput is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        body = CouponPreviewInput(**payload)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        service = DiscountService()
        items = await service.resolve_preview_items(body.items, country=body.country)
        pricing, applied = await service.apply(body.code, items, shipping=0, country=body.country)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if applied is None:
        raise HTTPException(status_code=400, detail="Invalid coupon")
    return JSONResponse(
        content=json.loads(
            json.dumps(
                {
                    "code": applied.code,
                    "type": applied.type,
                    "amount": applied.amount,
                    "indicator": applied.indicator,
                    "computed": pricing.discount,
                    "subtotal": pricing.subtotal,
                    "shipping": 0,
                    "total": pricing.total,
                },
                cls=JSONEncoder,
            )
        )
    )
