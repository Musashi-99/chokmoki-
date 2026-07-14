from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from src.config import settings
import os


class MongoSingleton:
    _instance: Optional['MongoSingleton'] = None
    _client: Optional[AsyncIOMotorClient] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoSingleton, cls).__new__(cls)
        return cls._instance
    
    async def connect(self):
        if self._client is None:
            # Previous defaults (5/0) were sized for a single dev container,
            # not concurrent production load — idempotency checks, inventory
            # reservations, order writes, and every background consumer all
            # borrow from this same pool. Still fully overridable via env.
            max_pool_size = int(os.getenv("MONGODB_MAX_POOL_SIZE", "50"))
            min_pool_size = int(os.getenv("MONGODB_MIN_POOL_SIZE", "5"))
            max_idle_time_ms = int(os.getenv("MONGODB_MAX_IDLE_TIME_MS", "10000"))
            
            self._client = AsyncIOMotorClient(
                settings.mongodb_uri,
                maxPoolSize=max_pool_size,
                minPoolSize=min_pool_size,
                maxIdleTimeMS=max_idle_time_ms,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=15000,
            )
            await self._client.admin.command("ping")
        return self._client
    
    async def get_database(self):
        if self._client is None:
            await self.connect()
        return self._client[settings.mongodb_db_name]
    
    async def close(self):
        if self._client:
            self._client.close()
            self._client = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


db = MongoSingleton.get_instance()

