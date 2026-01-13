import redis.asyncio as redis
from typing import Optional
from src.config import settings
import os


class RedisSingleton:
    _instance: Optional['RedisSingleton'] = None
    _client: Optional[redis.Redis] = None
    _connection_pool: Optional[redis.ConnectionPool] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisSingleton, cls).__new__(cls)
        return cls._instance
    
    async def connect(self):
        if self._client is None:
            max_connections = int(os.getenv("REDIS_MAX_CONNECTIONS", "2"))
            socket_connect_timeout = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "3"))
            socket_timeout = int(os.getenv("REDIS_SOCKET_TIMEOUT", "3"))
            retry_on_timeout = os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true"
            
            self._connection_pool = redis.ConnectionPool.from_url(
                settings.redis_url,
                max_connections=max_connections,
                socket_connect_timeout=socket_connect_timeout,
                socket_timeout=socket_timeout,
                retry_on_timeout=retry_on_timeout,
                decode_responses=True
            )
            
            self._client = redis.Redis(connection_pool=self._connection_pool)
            await self._client.ping()
        return self._client
    
    async def get_client(self):
        if self._client is None:
            await self.connect()
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None
        if self._connection_pool:
            await self._connection_pool.disconnect()
            self._connection_pool = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


redis_client = RedisSingleton.get_instance()
