from typing import List, Optional
from src.database.connection import db
from src.models.shipping_address import ShippingAddress, ShippingAddressCreate, ShippingAddressUpdate
from src.plugins.logger import logger
from bson import ObjectId
from datetime import datetime

MAX_ADDRESSES_PER_USER = 5


class ShippingAddressService:
    COLLECTION_NAME = "shipping_addresses"
    
    async def create(self, address_data: ShippingAddressCreate) -> ShippingAddress:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        # Check if user already has 5 addresses
        existing_count = await collection.count_documents({"email": address_data.email})
        if existing_count >= MAX_ADDRESSES_PER_USER:
            raise ValueError(f"Maximum {MAX_ADDRESSES_PER_USER} shipping addresses allowed per user")
        
        # If this is set as default, unset other defaults for this user
        if address_data.is_default:
            await collection.update_many(
                {"email": address_data.email, "is_default": True},
                {"$set": {"is_default": False}}
            )
        
        address_dict = address_data.model_dump()
        address_dict["created_at"] = datetime.utcnow()
        address_dict["updated_at"] = datetime.utcnow()
        
        result = await collection.insert_one(address_dict)
        address_dict["_id"] = result.inserted_id
        
        logger.info(f"Shipping address created: {result.inserted_id} for email: {address_data.email}")
        return ShippingAddress(**address_dict)
    
    async def get_by_id(self, address_id: str) -> Optional[ShippingAddress]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        address = await collection.find_one({"_id": ObjectId(address_id)})
        if address:
            return ShippingAddress(**address)
        return None
    
    async def get_by_email(self, email: str) -> List[ShippingAddress]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        cursor = collection.find({"email": email}).sort("created_at", -1)
        addresses = []
        async for doc in cursor:
            addresses.append(ShippingAddress(**doc))
        
        return addresses
    
    async def update(self, address_id: str, update_data: ShippingAddressUpdate, email: str) -> Optional[ShippingAddress]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        # Verify the address belongs to the user
        existing = await collection.find_one({"_id": ObjectId(address_id), "email": email})
        if not existing:
            raise ValueError("Shipping address not found or access denied")
        
        update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
        
        # If setting as default, unset other defaults for this user
        if update_dict.get("is_default") is True:
            await collection.update_many(
                {"email": email, "is_default": True, "_id": {"$ne": ObjectId(address_id)}},
                {"$set": {"is_default": False}}
            )
        
        update_dict["updated_at"] = datetime.utcnow()
        
        result = await collection.update_one(
            {"_id": ObjectId(address_id)},
            {"$set": update_dict}
        )
        
        if result.modified_count == 0:
            return None
        
        updated = await collection.find_one({"_id": ObjectId(address_id)})
        if updated:
            logger.info(f"Shipping address updated: {address_id} for email: {email}")
            return ShippingAddress(**updated)
        return None
    
    async def delete(self, address_id: str, email: str) -> bool:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        # Verify the address belongs to the user
        result = await collection.delete_one({"_id": ObjectId(address_id), "email": email})
        
        if result.deleted_count > 0:
            logger.info(f"Shipping address deleted: {address_id} for email: {email}")
            return True
        return False
    
    async def count_by_email(self, email: str) -> int:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        return await collection.count_documents({"email": email})

