from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional
from bson import ObjectId
from datetime import datetime
import json
import sys
import platform
import asyncio
import os

# Optional imports – do NOT crash boot
try:
    from src.database.connection import db
    from src.database.redis_connection import redis_client
    from src.cqrs.router import CQRSRouter
    from src.plugins.logger import logger
    from src.config import settings
except Exception as e:
    print(f"Import error: {e}", file=sys.stderr)
    db = None
    redis_client = None
    CQRSRouter = None
    logger = None
    settings = None


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


# ✅ Export THIS ONLY
app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
                    "has_clerk_secret": bool(settings.clerk_secret_key),
                    "has_admin_key": bool(settings.admin_key),
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
