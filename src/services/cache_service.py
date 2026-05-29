import json
from typing import Optional
from src.database.redis_connection import redis_client


class CacheService:
    DEFAULT_TTL = 300  # 5 minutes
    
    @staticmethod
    async def get(key: str) -> Optional[str]:
        try:
            client = await redis_client.get_client()
            return await client.get(key)
        except Exception:
            return None
    
    @staticmethod
    async def set(key: str, value: str, ttl: int = DEFAULT_TTL) -> None:
        try:
            client = await redis_client.get_client()
            await client.setex(key, ttl, value)
        except Exception:
            pass
    
    @staticmethod
    async def delete(key: str) -> None:
        try:
            client = await redis_client.get_client()
            await client.delete(key)
        except Exception:
            pass
    
    @staticmethod
    async def delete_pattern(pattern: str) -> None:
        try:
            client = await redis_client.get_client()
            keys = await client.keys(pattern)
            if keys:
                await client.delete(*keys)
        except Exception:
            pass


cache = CacheService()
