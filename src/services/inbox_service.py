from datetime import datetime
from typing import Any, Dict, List, Optional
from bson import ObjectId
from src.database.connection import db
from src.models.inbox import (
    ContactSubmission,
    ContactSubmissionCreate,
    NewsletterSubscription,
    NewsletterSubscribeCreate,
)
from src.plugins.logger import logger


class InboxService:
    CONTACT_COLLECTION = "contact_submissions"
    NEWSLETTER_COLLECTION = "newsletter_subscriptions"

    async def create_contact(self, data: ContactSubmissionCreate) -> ContactSubmission:
        database = await db.get_database()
        doc = data.model_dump()
        doc["read"] = False
        doc["created_at"] = datetime.utcnow()
        result = await database[self.CONTACT_COLLECTION].insert_one(doc)
        doc["_id"] = result.inserted_id
        logger.info(f"Contact submission: {result.inserted_id}")
        return ContactSubmission(**doc)

    async def list_contacts(
        self, skip: int = 0, limit: int = 100, unread_only: bool = False
    ) -> List[Dict[str, Any]]:
        database = await db.get_database()
        query: Dict[str, Any] = {}
        if unread_only:
            query["read"] = False
        cursor = (
            database[self.CONTACT_COLLECTION]
            .find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [ContactSubmission(**doc).model_dump(by_alias=True) for doc in docs]

    async def count_contacts(self, unread_only: bool = False) -> int:
        database = await db.get_database()
        query: Dict[str, Any] = {}
        if unread_only:
            query["read"] = False
        return await database[self.CONTACT_COLLECTION].count_documents(query)

    async def mark_contact_read(self, submission_id: str, read: bool = True) -> bool:
        database = await db.get_database()
        result = await database[self.CONTACT_COLLECTION].update_one(
            {"_id": ObjectId(submission_id)}, {"$set": {"read": read}}
        )
        return result.modified_count > 0

    async def delete_contact(self, submission_id: str) -> bool:
        database = await db.get_database()
        result = await database[self.CONTACT_COLLECTION].delete_one(
            {"_id": ObjectId(submission_id)}
        )
        return result.deleted_count > 0

    async def subscribe_newsletter(self, data: NewsletterSubscribeCreate) -> NewsletterSubscription:
        database = await db.get_database()
        collection = database[self.NEWSLETTER_COLLECTION]
        email = data.email.strip().lower()
        existing = await collection.find_one({"email": email})
        if existing:
            now = datetime.utcnow()
            await collection.update_one(
                {"_id": existing["_id"]},
                {"$set": {"source": data.source, "read": False, "created_at": now}},
            )
            existing["source"] = data.source
            existing["read"] = False
            existing["created_at"] = now
            return NewsletterSubscription(**existing)

        doc = {"email": email, "source": data.source, "read": False, "created_at": datetime.utcnow()}
        result = await collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        logger.info(f"Newsletter subscription: {email}")
        return NewsletterSubscription(**doc)

    async def list_newsletter(
        self, skip: int = 0, limit: int = 200, unread_only: bool = False
    ) -> List[Dict[str, Any]]:
        database = await db.get_database()
        query: Dict[str, Any] = {}
        if unread_only:
            query["read"] = False
        cursor = (
            database[self.NEWSLETTER_COLLECTION]
            .find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [NewsletterSubscription(**doc).model_dump(by_alias=True) for doc in docs]

    async def count_newsletter(self, unread_only: bool = False) -> int:
        database = await db.get_database()
        query: Dict[str, Any] = {}
        if unread_only:
            query["read"] = False
        return await database[self.NEWSLETTER_COLLECTION].count_documents(query)

    async def mark_newsletter_read(self, sub_id: str, read: bool = True) -> bool:
        database = await db.get_database()
        result = await database[self.NEWSLETTER_COLLECTION].update_one(
            {"_id": ObjectId(sub_id)}, {"$set": {"read": read}}
        )
        return result.modified_count > 0

    async def delete_newsletter(self, sub_id: str) -> bool:
        database = await db.get_database()
        result = await database[self.NEWSLETTER_COLLECTION].delete_one(
            {"_id": ObjectId(sub_id)}
        )
        return result.deleted_count > 0
