"""Health/liveness/readiness probes and Prometheus metrics."""
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, Response
from datetime import datetime, timezone
import asyncio
import os
import platform
from api.bootstrap import CQRSRouter, db, logger, redis_client, render_metrics, require_admin, settings

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok"}

@router.get("/health/live")
async def health_live():
    """Public liveness probe — no infrastructure details."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/health/ready")
async def health_ready():
    """Readiness probe — verifies DB and Redis connectivity without exposing stats."""
    db_ok = False
    redis_ok = False

    if db is not None:
        try:
            database = await db.get_database()
            await database.command("ping")
            db_ok = True
        except Exception:
            db_ok = False

    if redis_client is not None:
        try:
            client = await redis_client.get_client()
            await client.ping()
            redis_ok = True
        except Exception:
            redis_ok = False

    status_value = "ready" if db_ok and redis_ok else "not_ready"
    code = 200 if db_ok and redis_ok else 503
    return JSONResponse(
        status_code=code,
        content={
            "status": status_value,
            "database": "connected" if db_ok else "unavailable",
            "redis": "connected" if redis_ok else "unavailable",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

@router.get("/health/detail")
async def health_detail(email: str = Depends(require_admin)):
    """Admin-only detailed infrastructure statistics."""
    
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
                    "has_admin_login": bool(
                        settings.admin_email and settings.admin_password_configured
                    ),
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


@router.get("/metrics")
async def metrics(request: Request):
    if settings is None or render_metrics is None:
        raise HTTPException(status_code=500, detail="Metrics not initialized")
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Not found")

    if settings.is_production:
        token = (request.headers.get("X-Metrics-Token") or "").strip()
        if not settings.metrics_token or token != settings.metrics_token:
            raise HTTPException(status_code=401, detail="Unauthorized")

    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)
