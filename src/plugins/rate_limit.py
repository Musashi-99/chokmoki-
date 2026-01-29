from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable, Optional
import re
import json as json_lib
from src.database.redis_connection import redis_client
from src.config import settings


def parse_time_to_seconds(time_str: str) -> int:
    """Parse time string (e.g., '3m', '24h', '30s') to seconds"""
    if not time_str:
        return 60
    
    time_str = time_str.strip().lower()
    
    match = re.match(r'^(\d+)([smhd])$', time_str)
    if not match:
        raise ValueError(f"Invalid time format: {time_str}. Use format like '3m', '24h', '30s'")
    
    value, unit = match.groups()
    value = int(value)
    
    multipliers = {
        's': 1,
        'm': 60,
        'h': 60 * 60,
        'd': 24 * 60 * 60
    }
    
    return value * multipliers[unit]


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies"""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    if request.client:
        return request.client.host
    
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    ORDER_OPERATIONS = {"order.create", "order.initiate"}
    
    def __init__(self, app):
        super().__init__(app)
        self.normal_get_limit = settings.rate_limit_normal_get
        self.normal_post_limit = settings.rate_limit_normal_post
        self.normal_time_window = parse_time_to_seconds(settings.rate_limit_normal_time)
        self.order_max_limit = settings.rate_limit_order_max
        self.order_time_window = parse_time_to_seconds(settings.rate_limit_order_time)
    
    async def dispatch(self, request: Request, call_next: Callable):
        if not settings.rate_limit_enabled:
            return await call_next(request)
        
        if request.url.path in ["/health", "/webhook/razorpay"]:
            return await call_next(request)
        
        client_ip = get_client_ip(request)
        if client_ip == "unknown":
            return await call_next(request)
        
        try:
            redis = await redis_client.get_client()
            
            if request.method == "POST" and request.url.path == "/":
                operation = await self._extract_operation(request)
                
                if operation in self.ORDER_OPERATIONS:
                    allowed = await self._check_order_rate_limit(redis, client_ip)
                    if not allowed:
                        return JSONResponse(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            content={
                                "error": "Rate limit exceeded",
                                "message": f"Maximum {self.order_max_limit} order placements allowed per {settings.rate_limit_order_time}",
                                "retry_after": self.order_time_window
                            }
                        )
                else:
                    allowed = await self._check_normal_rate_limit(redis, client_ip, "POST")
                    if not allowed:
                        return JSONResponse(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            content={
                                "error": "Rate limit exceeded",
                                "message": f"Maximum {self.normal_post_limit} POST requests allowed per {settings.rate_limit_normal_time}",
                                "retry_after": self.normal_time_window
                            }
                        )
            elif request.method == "GET":
                allowed = await self._check_normal_rate_limit(redis, client_ip, "GET")
                if not allowed:
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "error": "Rate limit exceeded",
                            "message": f"Maximum {self.normal_get_limit} GET requests allowed per {settings.rate_limit_normal_time}",
                            "retry_after": self.normal_time_window
                        }
                    )
            
            return await call_next(request)
        
        except Exception as e:
            return await call_next(request)
    
    async def _extract_operation(self, request: Request) -> Optional[str]:
        """Extract operation from request body and preserve body for endpoint"""
        try:
            body_bytes = await request.body()
            if not body_bytes:
                return None
            
            data = json_lib.loads(body_bytes)
            operation = data.get("operation")
            
            async def receive() -> dict:
                return {"type": "http.request", "body": body_bytes}
            
            request._receive = receive
            return operation
        except:
            return None
    
    async def _check_normal_rate_limit(self, redis, client_ip: str, method: str) -> bool:
        """Check normal rate limit using token bucket algorithm"""
        limit = self.normal_get_limit if method == "GET" else self.normal_post_limit
        window = self.normal_time_window
        
        key = f"rate_limit:normal:{method}:{client_ip}"
        
        current = await redis.get(key)
        if current is None:
            await redis.setex(key, window, 1)
            return True
        
        count = int(current)
        if count >= limit:
            return False
        
        await redis.incr(key)
        ttl = await redis.ttl(key)
        if ttl == -1:
            await redis.expire(key, window)
        
        return True
    
    async def _check_order_rate_limit(self, redis, client_ip: str) -> bool:
        """Check order placement rate limit using token bucket algorithm"""
        key = f"rate_limit:order:{client_ip}"
        
        current = await redis.get(key)
        if current is None:
            await redis.setex(key, self.order_time_window, 1)
            return True
        
        count = int(current)
        if count >= self.order_max_limit:
            return False
        
        await redis.incr(key)
        ttl = await redis.ttl(key)
        if ttl == -1:
            await redis.expire(key, self.order_time_window)
        
        return True
