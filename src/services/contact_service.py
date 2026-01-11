from typing import List, Optional
from src.database.connection import db
from src.models.contact import Contact, ContactCreate
from src.plugins.logger import logger


class ContactService:
    COLLECTION_NAME = "contacts"
    
    async def create(self, contact_data: ContactCreate) -> Contact:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        from datetime import datetime
        contact_dict = contact_data.model_dump()
        contact_dict["created_at"] = datetime.utcnow()
        
        result = await collection.insert_one(contact_dict)
        contact_dict["_id"] = result.inserted_id
        
        logger.info(f"Contact submission created: {result.inserted_id}")
        return Contact(**contact_dict)
    
    async def get_by_id(self, contact_id: str) -> Optional[Contact]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        from bson import ObjectId
        contact = await collection.find_one({"_id": ObjectId(contact_id)})
        if contact:
            return Contact(**contact)
        return None
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[Contact]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        cursor = collection.find().sort("created_at", -1).skip(skip).limit(limit)
        contacts = []
        async for doc in cursor:
            contacts.append(Contact(**doc))
        
        return contacts
    
    async def count(self) -> int:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        return await collection.count_documents({})

