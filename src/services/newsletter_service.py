from typing import Optional, List
from src.database.connection import db
from src.models.newsletter import Newsletter, NewsletterCreate
from src.plugins.logger import logger


class NewsletterService:
    COLLECTION_NAME = "newsletters"
    
    async def exists(self, email: str) -> bool:
        """Check if email already exists in newsletter subscriptions"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        existing = await collection.find_one({"email": email.lower()})
        return existing is not None
    
    async def create(self, newsletter_data: NewsletterCreate) -> Newsletter:
        """Create a new newsletter subscription"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        email = newsletter_data.email.lower()
        
        # Check if email already exists
        if await self.exists(email):
            raise ValueError("Email already exists")
        
        from datetime import datetime
        newsletter_dict = {"email": email, "created_at": datetime.utcnow()}
        result = await collection.insert_one(newsletter_dict)
        newsletter_dict["_id"] = result.inserted_id
        
        logger.info(f"Newsletter subscription created for {email}")
        return Newsletter(**newsletter_dict)
    
    async def get_by_email(self, email: str) -> Optional[Newsletter]:
        """Get newsletter subscription by email"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        doc = await collection.find_one({"email": email.lower()})
        if doc:
            return Newsletter(**doc)
        return None
    
    async def list(self, skip: int = 0, limit: int = 100) -> List[Newsletter]:
        """List all newsletter subscriptions (admin only)"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        cursor = collection.find().skip(skip).limit(limit).sort("created_at", -1)
        newsletters = []
        async for doc in cursor:
            newsletters.append(Newsletter(**doc))
        return newsletters
