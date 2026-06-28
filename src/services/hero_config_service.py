import json
from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
from src.database.connection import db
from src.models.hero_config import HeroConfig, HeroConfigCreate
from src.services.cache_service import cache
from src.utils.mongo_json import mongo_json_dumps
from src.plugins.logger import logger


class HeroConfigService:
    COLLECTION_NAME = "hero_configs"
    CACHE_PREFIX = "chokmoki:hero_config"
    CACHE_TTL = 300
    
    async def create(self, data: HeroConfigCreate) -> HeroConfig:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        doc = data.model_dump()
        doc["updated_at"] = datetime.utcnow()
        result = await collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        
        await cache.delete_pattern(f"{self.CACHE_PREFIX}:*")
        logger.info(f"Hero config created: {result.inserted_id}")
        return HeroConfig(**doc)
    
    async def get_by_id(self, config_id: str) -> Optional[HeroConfig]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        doc = await collection.find_one({"_id": ObjectId(config_id)})
        if doc:
            return HeroConfig(**doc)
        return None
    
    async def get_active(self) -> Optional[HeroConfig]:
        cache_key = f"{self.CACHE_PREFIX}:active"
        cached = await cache.get(cache_key)
        if cached:
            return HeroConfig(**json.loads(cached))
        
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        doc = await collection.find_one({"active": True}, sort=[("updated_at", -1)])
        if doc:
            config = HeroConfig(**doc)
            await cache.set(cache_key, mongo_json_dumps(config.model_dump(by_alias=True)), self.CACHE_TTL)
            return config
        return None
    
    async def list(self, limit: int = 20) -> List[Dict[str, Any]]:
        cache_key = f"{self.CACHE_PREFIX}:list:{limit}"
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)
        
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        cursor = collection.find().sort("updated_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        result = [HeroConfig(**doc).model_dump(by_alias=True) for doc in docs]
        
        await cache.set(cache_key, mongo_json_dumps(result), self.CACHE_TTL)
        return result
    
    async def count(self) -> int:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        return await collection.count_documents({})
    
    async def update(self, config_id: str, update_data: Dict[str, Any]) -> Optional[HeroConfig]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        update_data["updated_at"] = datetime.utcnow()
        result = await collection.update_one(
            {"_id": ObjectId(config_id)},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            return None
        await cache.delete_pattern(f"{self.CACHE_PREFIX}:*")
        return await self.get_by_id(config_id)
    
    async def delete(self, config_id: str) -> bool:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        result = await collection.delete_one({"_id": ObjectId(config_id)})
        if result.deleted_count > 0:
            await cache.delete_pattern(f"{self.CACHE_PREFIX}:*")
        return result.deleted_count > 0
