from typing import List, Optional
from bson import ObjectId
from src.database.connection import db
from src.models.order import Order, OrderCreate, OrderStatus
from src.plugins.logger import logger


class OrderService:
    COLLECTION_NAME = "orders"
    
    async def create(self, order_data: OrderCreate) -> Order:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        order_dict = order_data.model_dump()
        order_dict["status"] = OrderStatus(type="accepted").model_dump()
        
        result = await collection.insert_one(order_dict)
        order_dict["_id"] = result.inserted_id
        
        logger.info(f"Order created: {result.inserted_id}")
        return Order(**order_dict)
    
    async def get_by_id(self, order_id: str) -> Optional[Order]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        order = await collection.find_one({"_id": ObjectId(order_id)})
        if order:
            return Order(**order)
        return None
    
    async def list(self, skip: int = 0, limit: int = 20) -> List[Order]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        cursor = collection.find({}).skip(skip).limit(limit)
        orders = await cursor.to_list(length=limit)
        
        return [Order(**order) for order in orders]
    
    async def update_status(
        self,
        order_id: str,
        status: OrderStatus
    ) -> Optional[Order]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        result = await collection.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"status": status.model_dump()}}
        )
        
        if result.modified_count > 0:
            return await self.get_by_id(order_id)
        return None

