import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from bson import ObjectId
from src.database.connection import db
from src.models.blog_post import (
    BlogPost,
    BlogPostCreate,
    JournalPageSettings,
    JournalPageSettingsUpdate,
)
from src.services.cache_service import cache
from src.utils.mongo_json import mongo_json_dumps
from src.plugins.logger import logger

JOURNAL_KEY = "main"
JOURNAL_CACHE = "chokmoki:journal_page"
POSTS_CACHE_PREFIX = "chokmoki:blog_posts"
CACHE_TTL = 300


class BlogService:
    POSTS_COLLECTION = "blog_posts"
    JOURNAL_COLLECTION = "journal_page_settings"

    async def get_journal_public(self) -> Optional[Dict[str, Any]]:
        cached = await cache.get(JOURNAL_CACHE)
        if cached:
            return json.loads(cached)

        database = await db.get_database()
        doc = await database[self.JOURNAL_COLLECTION].find_one(
            {"settings_key": JOURNAL_KEY, "active": True}
        )
        if not doc:
            return None

        result = JournalPageSettings(**doc).model_dump(by_alias=True)
        await cache.set(JOURNAL_CACHE, mongo_json_dumps(result), 600)
        return result

    async def get_journal_admin(self) -> Optional[JournalPageSettings]:
        database = await db.get_database()
        doc = await database[self.JOURNAL_COLLECTION].find_one({"settings_key": JOURNAL_KEY})
        if doc:
            return JournalPageSettings(**doc)
        return None

    async def upsert_journal(self, data: JournalPageSettingsUpdate) -> JournalPageSettings:
        database = await db.get_database()
        collection = database[self.JOURNAL_COLLECTION]
        payload = data.model_dump(exclude_unset=True)
        payload["updated_at"] = datetime.utcnow()
        payload["settings_key"] = JOURNAL_KEY

        existing = await collection.find_one({"settings_key": JOURNAL_KEY})
        if existing:
            await collection.update_one({"settings_key": JOURNAL_KEY}, {"$set": payload})
            doc = await collection.find_one({"settings_key": JOURNAL_KEY})
        else:
            payload.setdefault("active", True)
            result = await collection.insert_one(payload)
            doc = await collection.find_one({"_id": result.inserted_id})

        await cache.delete(JOURNAL_CACHE)
        await cache.delete_pattern(f"{POSTS_CACHE_PREFIX}:*")
        return JournalPageSettings(**doc)

    async def list_posts(
        self, active: Optional[bool] = None, skip: int = 0, limit: int = 50
    ) -> List[Dict[str, Any]]:
        cache_key = f"{POSTS_CACHE_PREFIX}:list:{active}:{skip}:{limit}"
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)

        database = await db.get_database()
        query: Dict[str, Any] = {}
        if active is not None:
            query["active"] = active

        cursor = (
            database[self.POSTS_COLLECTION]
            .find(query)
            .sort([("featured", -1), ("sort_order", 1), ("created_at", -1)])
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        result = [BlogPost(**doc).model_dump(by_alias=True) for doc in docs]
        await cache.set(cache_key, mongo_json_dumps(result), CACHE_TTL)
        return result

    async def count_posts(self, active: Optional[bool] = None) -> int:
        database = await db.get_database()
        query: Dict[str, Any] = {}
        if active is not None:
            query["active"] = active
        return await database[self.POSTS_COLLECTION].count_documents(query)

    async def get_post_by_slug(self, slug: str) -> Optional[BlogPost]:
        database = await db.get_database()
        doc = await database[self.POSTS_COLLECTION].find_one({"slug": slug, "active": True})
        if doc:
            return BlogPost(**doc)
        return None

    async def get_post_by_id(self, post_id: str) -> Optional[BlogPost]:
        database = await db.get_database()
        doc = await database[self.POSTS_COLLECTION].find_one({"_id": ObjectId(post_id)})
        if doc:
            return BlogPost(**doc)
        return None

    async def create_post(self, data: BlogPostCreate) -> BlogPost:
        database = await db.get_database()
        doc = data.model_dump()
        now = datetime.utcnow()
        doc["created_at"] = now
        doc["updated_at"] = now
        result = await database[self.POSTS_COLLECTION].insert_one(doc)
        doc["_id"] = result.inserted_id
        await cache.delete_pattern(f"{POSTS_CACHE_PREFIX}:*")
        logger.info(f"Blog post created: {result.inserted_id}")
        return BlogPost(**doc)

    async def update_post(self, post_id: str, update_data: Dict[str, Any]) -> Optional[BlogPost]:
        database = await db.get_database()
        update_data["updated_at"] = datetime.utcnow()
        result = await database[self.POSTS_COLLECTION].update_one(
            {"_id": ObjectId(post_id)}, {"$set": update_data}
        )
        if result.modified_count > 0:
            await cache.delete_pattern(f"{POSTS_CACHE_PREFIX}:*")
            return await self.get_post_by_id(post_id)
        return None

    async def delete_post(self, post_id: str) -> bool:
        database = await db.get_database()
        result = await database[self.POSTS_COLLECTION].delete_one({"_id": ObjectId(post_id)})
        if result.deleted_count > 0:
            await cache.delete_pattern(f"{POSTS_CACHE_PREFIX}:*")
        return result.deleted_count > 0
