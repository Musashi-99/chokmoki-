from typing import List, Optional
from bson import ObjectId
from src.database.connection import db
from src.models.category import Category, CategoryCreate
from src.plugins.logger import logger


class CategoryService:
    COLLECTION_NAME = "categories"
    
    async def create(self, category_data: CategoryCreate) -> Category:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        category_dict = category_data.model_dump()
        result = await collection.insert_one(category_dict)
        category_dict["_id"] = result.inserted_id
        
        logger.info(f"Category created: {result.inserted_id}")
        return Category(**category_dict)
    
    async def get_by_id(self, category_id: str) -> Optional[Category]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        category = await collection.find_one({"_id": ObjectId(category_id)})
        if category:
            return Category(**category)
        return None
    
    async def list(self, skip: int = 0, limit: int = 20) -> List[Category]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        cursor = collection.find({}).skip(skip).limit(limit)
        categories = await cursor.to_list(length=limit)
        
        return [Category(**category) for category in categories]
    
    async def update(self, category_id: str, update_data: dict) -> Optional[Category]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        result = await collection.update_one(
            {"_id": ObjectId(category_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            return await self.get_by_id(category_id)
        return None
    
    async def delete(self, category_id: str) -> bool:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        result = await collection.delete_one({"_id": ObjectId(category_id)})
        return result.deleted_count > 0

