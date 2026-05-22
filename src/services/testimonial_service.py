import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from bson import ObjectId
from src.database.connection import db
from src.utils.mongo_json import mongo_json_dumps
from src.models.testimonial import Testimonial, TestimonialCreate
from src.services.cache_service import cache
from src.plugins.logger import logger


class TestimonialService:
    COLLECTION_NAME = "testimonials"
    CACHE_PREFIX = "chokmoki:testimonials"
    CACHE_TTL = 300
    
    async def create(self, data: TestimonialCreate) -> Testimonial:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        doc = data.model_dump()
        doc["created_at"] = datetime.utcnow()
        result = await collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        
        await cache.delete_pattern(f"{self.CACHE_PREFIX}:*")
        logger.info(f"Testimonial created: {result.inserted_id}")
        return Testimonial(**doc)
    
    async def get_by_id(self, testimonial_id: str) -> Optional[Testimonial]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        doc = await collection.find_one({"_id": ObjectId(testimonial_id)})
        if doc:
            return Testimonial(**doc)
        return None
    
    async def list(
        self,
        active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        cache_key = f"{self.CACHE_PREFIX}:list:{active if active is not None else 'all'}:{skip}:{limit}"
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)
        
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {}
        if active is not None:
            query["active"] = active
        
        cursor = collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        result = [Testimonial(**doc).model_dump(by_alias=True) for doc in docs]
        
        await cache.set(cache_key, mongo_json_dumps(result), self.CACHE_TTL)
        return result
    
    async def count(self, active: Optional[bool] = None) -> int:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {}
        if active is not None:
            query["active"] = active
        
        return await collection.count_documents(query)
    
    async def update(self, testimonial_id: str, update_data: Dict[str, Any]) -> Optional[Testimonial]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        result = await collection.update_one(
            {"_id": ObjectId(testimonial_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            await cache.delete_pattern(f"{self.CACHE_PREFIX}:*")
            return await self.get_by_id(testimonial_id)
        return None
    
    async def delete(self, testimonial_id: str) -> bool:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        result = await collection.delete_one({"_id": ObjectId(testimonial_id)})
        if result.deleted_count > 0:
            await cache.delete_pattern(f"{self.CACHE_PREFIX}:*")
        return result.deleted_count > 0
