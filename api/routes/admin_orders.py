"""Admin order management + dashboard stats."""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
import json
from api.bootstrap import (
    OrderService,
    OrderStatus,
    ProductService,
    db,
    get_client_ip,
    logger,
    require_admin,
)
from api.json_utils import JSONEncoder

router = APIRouter()


@router.get("/api/admin/orders")
async def admin_list_orders(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    search: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    email: str = Depends(require_admin),
):
    """List all orders for the admin dashboard with optional filtering."""
    if OrderService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    service = OrderService()
    orders = await service.list(
        skip=skip, limit=limit,
        status=status, search=search,
        from_date=from_date, to_date=to_date,
    )
    total = await service.count(
        status=status, search=search,
        from_date=from_date, to_date=to_date,
    )
    return JSONResponse(content=json.loads(json.dumps({
        "data": [order.model_dump(by_alias=True) for order in orders],
        "count": total,
    }, cls=JSONEncoder)))


@router.post("/api/admin/orders")
async def admin_create_order(
    request: Request, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Create an order from the admin dashboard (phone / manual orders)."""
    if OrderService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        service = OrderService()
        client_ip = get_client_ip(request) if get_client_ip else None
        order = await service.create_from_admin(payload, ip=client_ip)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if logger:
            logger.error(f"Admin order creation failed: {e}")
        raise HTTPException(status_code=500) from e

    return JSONResponse(
        content=json.loads(
            json.dumps(order.model_dump(by_alias=True), cls=JSONEncoder)
        )
    )


@router.put("/api/admin/orders/{order_id}/status")
async def admin_update_order_status(
    order_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update an order's status by order_id."""
    if OrderService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        status = OrderStatus(**payload.get("status", {}))
        service = OrderService()
        order = await service.get_by_id(order_id)
        if not order:
            order = await service.get_by_mongo_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        updated = await service.update_status(order.order_id, status)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not updated:
        raise HTTPException(status_code=404, detail="Order not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@router.get("/api/admin/orders/{order_id}")
async def admin_get_order(order_id: str, email: str = Depends(require_admin)):
    """Get a single order by order_id."""
    if OrderService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    service = OrderService()
    order = await service.get_by_id(order_id)
    if not order:
        order = await service.get_by_mongo_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return JSONResponse(content=json.loads(json.dumps(
        order.model_dump(by_alias=True), cls=JSONEncoder
    )))


@router.get("/api/admin/stats")
async def admin_get_stats(email: str = Depends(require_admin)):
    """Dashboard overview stats: order counts, revenue, product count."""
    if OrderService is None or ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    database = await db.get_database()

    orders_collection = database["orders"]
    products_collection = database["products"]

    total_orders = await orders_collection.count_documents({})

    revenue_pipeline = [
        {"$match": {"status.type": {"$nin": ["rejected", "rejected_by_user"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}},
    ]
    revenue_result = await orders_collection.aggregate(revenue_pipeline).to_list(1)
    total_revenue = revenue_result[0]["total"] if revenue_result else 0

    status_pipeline = [
        {"$group": {"_id": "$status.type", "count": {"$sum": 1}}},
    ]
    status_result = await orders_collection.aggregate(status_pipeline).to_list(100)
    status_counts = {item["_id"]: item["count"] for item in status_result if item["_id"]}

    # Align "today" with store timezone (IST) — Mongo stores naive UTC datetimes.
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)
    today_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = today_start_ist.astimezone(timezone.utc).replace(tzinfo=None)
    orders_today = await orders_collection.count_documents({"created_at": {"$gte": today_start}})

    total_products = await products_collection.count_documents({})
    active_products = await products_collection.count_documents({"active": True})

    return JSONResponse(content=json.loads(json.dumps({
        "totalOrders": total_orders,
        "totalRevenue": total_revenue,
        "ordersToday": orders_today,
        "statusCounts": status_counts,
        "totalProducts": total_products,
        "activeProducts": active_products,
    }, cls=JSONEncoder)))
