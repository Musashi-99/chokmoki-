from typing import Optional
import uuid
from src.database.connection import db
from src.plugins.logger import logger


class SyncKeyService:
    COLLECTION_NAME = "sync_keys"
    PRODUCTS_KEY = "products"
    
    async def get_or_create_products_sync_key(self) -> str:
        """Get or create products sync key"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        sync_key_doc = await collection.find_one({"key": self.PRODUCTS_KEY})
        
        if not sync_key_doc:
            new_sync_key = str(uuid.uuid4())
            await collection.insert_one({
                "key": self.PRODUCTS_KEY,
                "value": new_sync_key,
            })
            logger.info(f"Created products sync key: {new_sync_key}")
            return new_sync_key
        
        return sync_key_doc.get("value", "")
    
    async def update_products_sync_key(self) -> str:
        """Update products sync key (generates new UUID)"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        new_sync_key = str(uuid.uuid4())
        result = await collection.update_one(
            {"key": self.PRODUCTS_KEY},
            {"$set": {"value": new_sync_key}},
            upsert=True
        )
        
        logger.info(f"Updated products sync key: {new_sync_key}")
        return new_sync_key
    
    async def get_products_sync_key(self) -> Optional[str]:
        """Get current products sync key"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        sync_key_doc = await collection.find_one({"key": self.PRODUCTS_KEY})
        if sync_key_doc:
            return sync_key_doc.get("value")
        return None
