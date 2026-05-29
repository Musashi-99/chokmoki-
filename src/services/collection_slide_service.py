from typing import List, Optional, Dict, Any
from bson import ObjectId
import json
from src.database.connection import db
from src.models.collection_slide import CollectionSlide, CollectionSlideCreate
from src.services.cache_service import cache
from src.utils.mongo_json import mongo_json_dumps
from src.plugins.logger import logger


class CollectionSlideService:
    COLLECTION_NAME = "collection_slides"
    CACHE_PREFIX = "chokmoki:collection_slides"
    CACHE_TTL = 600
    
    async def create(self, data: CollectionSlideCreate) -> CollectionSlide:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        doc = data.model_dump()
        result = await collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        
        await self._invalidate_cache()
        logger.info(f"Collection slide created: {result.inserted_id}")
        return CollectionSlide(**doc)
    
    async def get_by_id(self, slide_id: str) -> Optional[CollectionSlide]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        doc = await collection.find_one({"_id": ObjectId(slide_id)})
        if doc:
            return CollectionSlide(**doc)
        return None
    
    async def list(self, active: Optional[bool] = None) -> List[Dict[str, Any]]:
        cache_key = f"{self.CACHE_PREFIX}:{active if active is not None else 'all'}"
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)
        
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {}
        if active is not None:
            query["active"] = active
        
        cursor = collection.find(query).sort("sort_order", 1)
        docs = await cursor.to_list(length=100)
        result = [CollectionSlide(**doc).model_dump(by_alias=True) for doc in docs]
        
        await cache.set(cache_key, mongo_json_dumps(result), self.CACHE_TTL)
        return result
    
    async def update(self, slide_id: str, update_data: Dict[str, Any]) -> Optional[CollectionSlide]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        result = await collection.update_one(
            {"_id": ObjectId(slide_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            await self._invalidate_cache()
            return await self.get_by_id(slide_id)
        return None
    
    async def delete(self, slide_id: str) -> bool:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        result = await collection.delete_one({"_id": ObjectId(slide_id)})
        if result.deleted_count > 0:
            await self._invalidate_cache()
        return result.deleted_count > 0
    
    async def _invalidate_cache(self):
        await cache.delete_pattern(f"{self.CACHE_PREFIX}:*")
