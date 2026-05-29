from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
import json
from src.database.connection import db
from src.models.site_asset import SiteAsset, SiteAssetCreate
from src.services.cache_service import cache
from src.utils.mongo_json import mongo_json_dumps
from src.plugins.logger import logger


class SiteAssetService:
    COLLECTION_NAME = "site_assets"
    CACHE_PREFIX = "chokmoki:site_assets"
    CACHE_TTL = 600
    
    async def create(self, data: SiteAssetCreate) -> SiteAsset:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        doc = data.model_dump()
        doc["updated_at"] = datetime.utcnow()
        result = await collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        
        await cache.delete_pattern(f"{self.CACHE_PREFIX}:*")
        logger.info(f"Site asset created: {result.inserted_id}")
        return SiteAsset(**doc)
    
    async def get_by_id(self, asset_id: str) -> Optional[SiteAsset]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        doc = await collection.find_one({"_id": ObjectId(asset_id)})
        if doc:
            return SiteAsset(**doc)
        return None
    
    async def get_by_key(self, key: str) -> Optional[SiteAsset]:
        cache_key = f"{self.CACHE_PREFIX}:key:{key}"
        cached = await cache.get(cache_key)
        if cached:
            return SiteAsset(**json.loads(cached))
        
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        doc = await collection.find_one({"key": key, "active": True})
        if doc:
            asset = SiteAsset(**doc)
            await cache.set(cache_key, mongo_json_dumps(asset.model_dump(by_alias=True)), self.CACHE_TTL)
            return asset
        return None
    
    async def list(self, active: Optional[bool] = None) -> List[Dict[str, Any]]:
        cache_key = f"{self.CACHE_PREFIX}:list:{active if active is not None else 'all'}"
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)
        
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {}
        if active is not None:
            query["active"] = active
        
        cursor = collection.find(query).sort("updated_at", -1)
        docs = await cursor.to_list(length=100)
        result = [SiteAsset(**doc).model_dump(by_alias=True) for doc in docs]
        
        await cache.set(cache_key, mongo_json_dumps(result), self.CACHE_TTL)
        return result
    
    async def update(self, asset_id: str, update_data: Dict[str, Any]) -> Optional[SiteAsset]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        update_data["updated_at"] = datetime.utcnow()
        result = await collection.update_one(
            {"_id": ObjectId(asset_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            await cache.delete_pattern(f"{self.CACHE_PREFIX}:*")
            return await self.get_by_id(asset_id)
        return None
    
    async def delete(self, asset_id: str) -> bool:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        result = await collection.delete_one({"_id": ObjectId(asset_id)})
        if result.deleted_count > 0:
            await cache.delete_pattern(f"{self.CACHE_PREFIX}:*")
        return result.deleted_count > 0
