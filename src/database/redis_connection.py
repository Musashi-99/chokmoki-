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
            # Previous default (2) was sized for a single dev container —
            # this shared pool serves idempotency checks, inventory locks/
            # reservations, rate limiting, and stream XADD calls all at
            # once, so it's a real contention point under concurrent load.
            # Still fully overridable via env. health_check_interval
            # proactively pings idle pooled connections so a half-dead
            # socket gets detected and replaced instead of surfacing as a
            # mysterious failure on the next borrow.
            max_connections = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))
            socket_connect_timeout = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "3"))
            socket_timeout = int(os.getenv("REDIS_SOCKET_TIMEOUT", "3"))
            retry_on_timeout = os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true"
            health_check_interval = int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))

            self._connection_pool = redis.ConnectionPool.from_url(
                settings.redis_url,
                max_connections=max_connections,
                socket_connect_timeout=socket_connect_timeout,
                socket_timeout=socket_timeout,
                retry_on_timeout=retry_on_timeout,
                health_check_interval=health_check_interval,
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
