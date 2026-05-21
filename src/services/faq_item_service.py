from typing import List, Optional, Dict, Any
from bson import ObjectId
import json
from src.database.connection import db
from src.models.faq_item import FAQItem, FAQItemCreate
from src.services.cache_service import cache
from src.utils.mongo_json import mongo_json_dumps
from src.plugins.logger import logger


class FAQItemService:
    COLLECTION_NAME = "faq_items"
    CACHE_PREFIX = "chokmoki:faq"
    CACHE_TTL = 600
    
    async def create(self, data: FAQItemCreate) -> FAQItem:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        doc = data.model_dump()
        result = await collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        
        await self._invalidate_cache()
        logger.info(f"FAQ item created: {result.inserted_id}")
        return FAQItem(**doc)
    
    async def get_by_id(self, faq_id: str) -> Optional[FAQItem]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        doc = await collection.find_one({"_id": ObjectId(faq_id)})
        if doc:
            return FAQItem(**doc)
        return None
    
    async def list(self, scope: Optional[str] = None, active: Optional[bool] = None) -> List[Dict[str, Any]]:
        cache_key = f"{self.CACHE_PREFIX}:{scope or 'all'}:{active if active is not None else 'all'}"
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)
        
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {}
        if active is not None:
            query["active"] = active
        if scope:
            query["$or"] = [{"scope": scope}, {"scope": "both"}]
        
        cursor = collection.find(query).sort("sort_order", 1)
        docs = await cursor.to_list(length=100)
        result = [FAQItem(**doc).model_dump(by_alias=True) for doc in docs]
        
        await cache.set(cache_key, mongo_json_dumps(result), self.CACHE_TTL)
        return result
    
    async def update(self, faq_id: str, update_data: Dict[str, Any]) -> Optional[FAQItem]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        result = await collection.update_one(
            {"_id": ObjectId(faq_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            await self._invalidate_cache()
            return await self.get_by_id(faq_id)
        return None
    
    async def delete(self, faq_id: str) -> bool:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        result = await collection.delete_one({"_id": ObjectId(faq_id)})
        if result.deleted_count > 0:
            await self._invalidate_cache()
        return result.deleted_count > 0
    
    async def _invalidate_cache(self):
        await cache.delete_pattern(f"{self.CACHE_PREFIX}:*")
