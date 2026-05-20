from fastapi import FastAPI, HTTPException, Request, Header, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager
from bson import ObjectId
from datetime import datetime
import json
import sys
import platform
import asyncio
import os

from dotenv import load_dotenv

load_dotenv(override=False)

# Optional imports – do NOT crash boot
try:
    from src.database.connection import db
    from src.database.redis_connection import redis_client
    from src.cqrs.router import CQRSRouter
    from src.services.razorpay_service import RazorpayService
    from src.services.order_service import OrderService
    from src.services.telegram_service import TelegramService
    from src.plugins.logger import logger
    from src.config import settings
    from src.plugins.rate_limit import RateLimitMiddleware
    from src.services.product_service import ProductService
    from src.services.category_service import CategoryService
    from src.models.product import JewelryProductCreate
    from src.models.category import JewelryCategoryCreate
    from src.models.order import OrderCreateInput
    from src.services.admin_auth_service import AdminAuthService
    from src.services.r2_service import R2Service
except Exception as e:
    print(f"Import error: {e}", file=sys.stderr)
    db = None
    redis_client = None
    CQRSRouter = None
    RazorpayService = None
    OrderService = None
    TelegramService = None
    logger = None
    settings = None
    RateLimitMiddleware = None
    ProductService = None
    CategoryService = None
    JewelryProductCreate = None
    JewelryCategoryCreate = None
    OrderCreateInput = None
    AdminAuthService = None
    R2Service = None


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class APIRequest(BaseModel):
    type: str
    operation: str
    params: Dict[str, Any] = {}
    adminKey: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database and Redis connections lifecycle"""
    try:
        if db:
            await db.connect()
        if redis_client:
            await redis_client.connect()
        # Ensure the R2 media bucket exists for dynamic asset hosting
        if R2Service is not None:
            try:
                R2Service().ensure_bucket()
            except Exception as r2_err:
                if logger:
                    logger.warning(f"R2 bucket check skipped: {r2_err}")
    except Exception as e:
        if logger:
            logger.error(f"Startup connection error: {e}")
        print(f"Startup connection error: {e}", file=sys.stderr)
    
    yield
    
    try:
        if db:
            await db.close()
        if redis_client:
            await redis_client.close()
    except Exception as e:
        if logger:
            logger.error(f"Shutdown connection error: {e}")
        print(f"Shutdown connection error: {e}", file=sys.stderr)


# Export THIS ONLY
app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if RateLimitMiddleware:
    app.add_middleware(RateLimitMiddleware)


# ========== REST API Endpoints for Frontend ==========

@app.get("/api/products")
async def api_list_products(
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
):
    """List products with optional filtering"""
    if ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = ProductService()
    products = await service.list(
        skip=skip, limit=limit, active=True,
        category=category, sort=sort, search=search
    )
    total = await service.count(active=True, category=category, search=search)
    
    return JSONResponse(
        content=json.loads(json.dumps({
            "data": products,
            "count": total
        }, cls=JSONEncoder))
    )


@app.get("/api/products/{slug}")
async def api_get_product(slug: str):
    """Get a single product by slug"""
    if ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = ProductService()
    product = await service.get_by_slug(slug)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return JSONResponse(
        content=json.loads(json.dumps(
            product.model_dump(by_alias=True),
            cls=JSONEncoder
        ))
    )


@app.get("/api/categories")
async def api_list_categories():
    """List all active categories"""
    if CategoryService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = CategoryService()
    categories = await service.list(active=True)
    total = await service.count(active=True)
    
    return JSONResponse(
        content=json.loads(json.dumps({
            "data": [cat.model_dump(by_alias=True) for cat in categories],
            "count": total
        }, cls=JSONEncoder))
    )


@app.get("/api/categories/{slug}")
async def api_get_category(slug: str):
    """Get a single category by slug"""
    if CategoryService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = CategoryService()
    category = await service.get_by_slug(slug)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    return JSONResponse(
        content=json.loads(json.dumps(
            category.model_dump(by_alias=True),
            cls=JSONEncoder
        ))
    )


@app.post("/api/orders")
async def api_create_order(payload: Dict[str, Any]):
    """Create a new order (public endpoint)."""
    if OrderService is None or OrderCreateInput is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        order_data = OrderCreateInput(**payload)
        service = OrderService()
        order = await service.create(order_data)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if logger:
            logger.error(f"Order creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create order: {str(e)}")

    return JSONResponse(
        content=json.loads(json.dumps(
            order.model_dump(by_alias=True),
            cls=JSONEncoder
        ))
    )


# ========== Admin Panel: Auth, Media Upload & Management ==========

class AdminLoginRequest(BaseModel):
    email: str
    password: str


async def require_admin(authorization: Optional[str] = Header(None)) -> str:
    """Validate the admin JWT from the 'Authorization: Bearer <token>' header."""
    if AdminAuthService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing admin token")
    token = authorization.split(" ", 1)[1].strip()
    email = AdminAuthService().verify_token(token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired admin token")
    return email


@app.post("/api/admin/login")
async def admin_login(payload: AdminLoginRequest):
    """Authenticate the super admin and return a JWT."""
    if AdminAuthService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    token = await AdminAuthService().authenticate(payload.email, payload.password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"token": token, "email": payload.email}


@app.get("/api/admin/me")
async def admin_me(email: str = Depends(require_admin)):
    """Return the currently authenticated admin (used to verify a stored token)."""
    return {"email": email}


@app.post("/api/admin/upload")
async def admin_upload(
    files: List[UploadFile] = File(...),
    folder: str = Form("products"),
    email: str = Depends(require_admin),
):
    """Upload one or more media files to the Cloudflare R2 'chokmoki' bucket."""
    if R2Service is None:
        raise HTTPException(status_code=500, detail="R2 storage not initialized")

    safe_folder = "".join(c for c in folder if c.isalnum() or c in ("-", "_", "/")) or "products"
    service = R2Service()
    urls: List[str] = []
    try:
        for upload in files:
            content = await upload.read()
            url = await service.upload_file(
                content, upload.filename or "upload.bin", folder=safe_folder
            )
            urls.append(url)
    except Exception as e:
        if logger:
            logger.error(f"Admin upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    return {"urls": urls}


@app.get("/api/admin/orders")
async def admin_list_orders(
    skip: int = 0, limit: int = 50, email: str = Depends(require_admin)
):
    """List all orders for the admin dashboard."""
    if OrderService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    service = OrderService()
    orders = await service.list(skip=skip, limit=limit)
    total = await service.count()
    return JSONResponse(content=json.loads(json.dumps({
        "data": [order.model_dump(by_alias=True) for order in orders],
        "count": total,
    }, cls=JSONEncoder)))


@app.get("/api/admin/products")
async def admin_list_products(
    skip: int = 0, limit: int = 200, email: str = Depends(require_admin)
):
    """List every product (including inactive) for the admin dashboard."""
    if ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    service = ProductService()
    products = await service.list(skip=skip, limit=limit)
    total = await service.count()
    return JSONResponse(content=json.loads(json.dumps({
        "data": products,
        "count": total,
    }, cls=JSONEncoder)))


@app.post("/api/admin/products")
async def admin_create_product(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Create a product. Media URLs should already point to R2 (see /api/admin/upload)."""
    if ProductService is None or JewelryProductCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        product_data = JewelryProductCreate(**payload)
        product = await ProductService().create(product_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return JSONResponse(content=json.loads(json.dumps(
        product.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.put("/api/admin/products/{product_id}")
async def admin_update_product(
    product_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a product by its MongoDB id."""
    if ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        updated = await ProductService().update(product_id, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Product not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.delete("/api/admin/products/{product_id}")
async def admin_delete_product(product_id: str, email: str = Depends(require_admin)):
    """Delete a product by its MongoDB id."""
    if ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        deleted = await ProductService().delete(product_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"success": True}


@app.get("/api/admin/categories")
async def admin_list_categories(email: str = Depends(require_admin)):
    """List every category for the admin dashboard."""
    if CategoryService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    service = CategoryService()
    categories = await service.list(limit=100)
    return JSONResponse(content=json.loads(json.dumps({
        "data": [cat.model_dump(by_alias=True) for cat in categories],
        "count": len(categories),
    }, cls=JSONEncoder)))


@app.post("/api/admin/categories")
async def admin_create_category(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Create a category."""
    if CategoryService is None or JewelryCategoryCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        category_data = JewelryCategoryCreate(**payload)
        category = await CategoryService().create(category_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return JSONResponse(content=json.loads(json.dumps(
        category.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.put("/api/admin/categories/{category_id}")
async def admin_update_category(
    category_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a category by its MongoDB id."""
    if CategoryService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        updated = await CategoryService().update(category_id, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Category not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.delete("/api/admin/categories/{category_id}")
async def admin_delete_category(category_id: str, email: str = Depends(require_admin)):
    """Delete a category by its MongoDB id."""
    if CategoryService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        deleted = await CategoryService().delete(category_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"success": True}


# ========== Existing CQRS Endpoint ==========

@app.post("/")
async def handle_request(request: APIRequest):
    if CQRSRouter is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    if request.type not in {"query", "mutation"}:
        raise HTTPException(status_code=400, detail="Invalid type")

    try:
        if request.type == "query":
            result = await CQRSRouter.execute_query(
                request.operation, request.params, request.adminKey
            )
        else:
            result = await CQRSRouter.execute_mutation(
                request.operation, request.params, request.adminKey
            )

        return JSONResponse(
            content=json.loads(json.dumps(result, cls=JSONEncoder))
        )

    except HTTPException:
        raise
    except Exception as e:
        if logger:
            logger.error(str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/webhook/razorpay")
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
            database = await db.get_database()
            orders_collection = database[order_service.COLLECTION_NAME]
            
            existing_order = await orders_collection.find_one({"order_id": order_id})
            if existing_order:
                logger.info(f"Order {order_id} already exists in MongoDB, skipping duplicate webhook processing")
                redis = await redis_client.get_client()
                redis_key = f"pending_order:{order_id}"
                await redis.delete(redis_key)
                return JSONResponse(content={"status": "success", "order_id": order_id, "message": "already_processed"})
            
            redis = await redis_client.get_client()
            redis_key = f"pending_order:{order_id}"
            
            order_json = await redis.get(redis_key)
            if not order_json:
                logger.warning(f"Order {order_id} not found in Redis, may already be processed")
                return JSONResponse(content={"status": "ignored", "reason": "order_not_found"})
            
            order_dict = json.loads(order_json)
            order_dict["payment_status"] = "completed"
            order_dict["razorpay_order_id"] = razorpay_order_id
            order_dict["razorpay_payment_id"] = razorpay_payment_id
            order_dict["created_at"] = datetime.fromisoformat(order_dict["created_at"])
            
            logs_collection = database[order_service.ORDER_LOGS_COLLECTION]
            
            try:
                result = await orders_collection.insert_one(order_dict)
                order_dict["_id"] = result.inserted_id
                
                await logs_collection.insert_one({
                    "order_id": order_id,
                    "raw_data": order_dict.get("raw_order_log", {}),
                    "created_at": datetime.utcnow()
                })
                
                # Push to Telegram queue (non-blocking, best-effort)
                if TelegramService:
                    telegram_service = TelegramService()
                    try:
                        await telegram_service.push_order_to_queue(order_dict)
                    except Exception as e:
                        if logger:
                            logger.warning(f"Failed to push order to Telegram queue: {e}")
                
                await redis.delete(redis_key)
                logger.info(f"Webhook processed: Order {order_id} moved from Redis to MongoDB")
                return JSONResponse(content={"status": "success", "order_id": order_id})
            except Exception as e:
                logger.error(f"Failed to process webhook for order {order_id}: {e}")
                await redis.delete(redis_key)
                raise HTTPException(status_code=500, detail=f"Failed to process order: {str(e)}")
        
        logger.info(f"Webhook event {event} received but not processed")
        return JSONResponse(content={"status": "ignored", "event": event})
    
    except HTTPException:
        raise
    except Exception as e:
        if logger:
            logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


@app.get("/health")
async def health_check():
    """Comprehensive health check with system stats, database stats, and environment info"""
    
    async def get_db_stats():
        """Get MongoDB database statistics"""
        try:
            if db is None:
                return {"status": "not_available", "error": "Database not initialized"}
            
            database = await db.get_database()
            
            # Get all collection names
            collections = await database.list_collection_names()
            
            # Get counts for main collections in parallel
            collection_tasks = []
            for collection_name in collections:
                collection = database[collection_name]
                collection_tasks.append(collection.count_documents({}))
            
            counts = await asyncio.gather(*collection_tasks, return_exceptions=True)
            
            collection_stats = {}
            for i, collection_name in enumerate(collections):
                count = counts[i]
                if isinstance(count, Exception):
                    collection_stats[collection_name] = {"count": 0, "error": str(count)}
                else:
                    collection_stats[collection_name] = {"count": count}
            
            # Get database stats
            db_stats = await database.command("dbStats")
            
            return {
                "status": "connected",
                "database_name": settings.mongodb_db_name if settings else "unknown",
                "collections": collection_stats,
                "database_size": {
                    "dataSize": db_stats.get("dataSize", 0),
                    "storageSize": db_stats.get("storageSize", 0),
                    "indexSize": db_stats.get("indexSize", 0),
                    "collections": db_stats.get("collections", 0),
                }
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def get_redis_stats():
        """Get Redis connection statistics"""
        try:
            if redis_client is None:
                return {"status": "not_available", "error": "Redis not initialized"}
            
            client = await redis_client.get_client()
            info = await client.info()
            
            return {
                "status": "connected",
                "redis_version": info.get("redis_version", "unknown"),
                "used_memory": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace": {
                    "keys": info.get("db0", {}).get("keys", 0) if "db0" in str(info) else 0
                }
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def get_environment_info():
        """Get environment and system information"""
        try:
            env_info = {}
            if settings:
                env_info = {
                    "mongodb_db_name": settings.mongodb_db_name,
                    "log_level": settings.log_level,
                    "has_admin_login": bool(settings.admin_email and settings.admin_password),
                    "has_redis_url": bool(settings.redis_url),
                }
            
            return {
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "system": platform.system(),
                "processor": platform.processor(),
                "environment": os.getenv("ENVIRONMENT", "development"),
                "settings": env_info
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def get_service_status():
        """Get status of various services"""
        return {
            "database": "available" if db is not None else "not_available",
            "redis": "available" if redis_client is not None else "not_available",
            "cqrs_router": "available" if CQRSRouter is not None else "not_available",
            "logger": "available" if logger is not None else "not_available",
        }
    
    # Fetch all stats in parallel
    db_stats_task = get_db_stats()
    redis_stats_task = get_redis_stats()
    env_info_task = get_environment_info()
    service_status_task = get_service_status()
    
    db_stats, redis_stats, env_info, service_status = await asyncio.gather(
        db_stats_task,
        redis_stats_task,
        env_info_task,
        service_status_task,
        return_exceptions=True
    )
    
    # Handle exceptions
    if isinstance(db_stats, Exception):
        db_stats = {"status": "error", "error": str(db_stats)}
    if isinstance(redis_stats, Exception):
        redis_stats = {"status": "error", "error": str(redis_stats)}
    if isinstance(env_info, Exception):
        env_info = {"error": str(env_info)}
    if isinstance(service_status, Exception):
        service_status = {"error": str(service_status)}
    
    # Determine overall health status
    overall_status = "healthy"
    if db_stats.get("status") != "connected":
        overall_status = "degraded"
    if redis_stats.get("status") != "connected":
        overall_status = "degraded"
    
    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "services": service_status,
        "database": db_stats,
        "redis": redis_stats,
        "environment": env_info,
    }


@app.post("/cron/telegram/notify")
async def telegram_notify_cron():
    """Cron endpoint to process and send Telegram notifications"""
    if TelegramService is None:
        raise HTTPException(status_code=500, detail="TelegramService not initialized")
    
    try:
        telegram_service = TelegramService()
        result = await telegram_service.process_and_send_notifications()
        
        if result.success:
            return JSONResponse(content=result.model_dump())
        else:
            raise HTTPException(status_code=500, detail=result.message)
    except HTTPException:
        raise
    except Exception as e:
        if logger:
            logger.error(f"Telegram cron error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
