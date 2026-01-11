from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from src.config import settings


class MongoSingleton:
    _instance: Optional[AsyncIOMotorClient] = None
    _client: Optional[AsyncIOMotorClient] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoSingleton, cls).__new__(cls)
        return cls._instance
    
    async def connect(self):
        if self._client is None:
            self._client = AsyncIOMotorClient(settings.mongodb_uri)
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

