import redis.asyncio as redis
from typing import Optional
from src.config import settings


class RedisSingleton:
    _instance: Optional['RedisSingleton'] = None
    _client: Optional[redis.Redis] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisSingleton, cls).__new__(cls)
        return cls._instance
    
    async def connect(self):
        if self._client is None:
            self._client = await redis.from_url(
                settings.redis_url,
                decode_responses=True
            )
        return self._client
    
    async def get_client(self):
        if self._client is None:
            await self.connect()
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


redis_client = RedisSingleton.get_instance()
