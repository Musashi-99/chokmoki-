from typing import Any, Dict, List, Optional
from datetime import datetime
import json
from bson import ObjectId
from src.database.connection import db
from src.models.policy_content import (
    PolicyPageMeta,
    PolicyPageMetaUpdate,
    PolicySection,
    PolicySectionCreate,
)
from src.services.cache_service import cache
from src.utils.mongo_json import mongo_json_dumps
from src.plugins.logger import logger

META_KEY = "main"
CACHE_KEY = "chokmoki:policies"
CACHE_TTL = 600


class PolicyContentService:
    META_COLLECTION = "policy_page_meta"
    SECTIONS_COLLECTION = "policy_sections"

    async def _invalidate(self) -> None:
        await cache.delete(CACHE_KEY)

    async def get_public_bundle(self) -> Dict[str, Any]:
        cached = await cache.get(CACHE_KEY)
        if cached:
            return json.loads(cached)

        database = await db.get_database()
        meta_doc = await database[self.META_COLLECTION].find_one(
            {"meta_key": META_KEY, "active": True}
        )
        meta = PolicyPageMeta(**meta_doc).model_dump(by_alias=True) if meta_doc else None

        cursor = database[self.SECTIONS_COLLECTION].find({"active": True}).sort(
            "sort_order", 1
        )
        sections = [
            PolicySection(**doc).model_dump(by_alias=True)
            for doc in await cursor.to_list(length=20)
            if doc.get("body", "").strip()
        ]

        bundle = {"meta": meta, "sections": sections, "count": len(sections)}
        await cache.set(CACHE_KEY, mongo_json_dumps(bundle), CACHE_TTL)
        return bundle

    async def get_admin_bundle(self) -> Dict[str, Any]:
        database = await db.get_database()
        meta_doc = await database[self.META_COLLECTION].find_one({"meta_key": META_KEY})
        meta = PolicyPageMeta(**meta_doc).model_dump(by_alias=True) if meta_doc else None

        cursor = database[self.SECTIONS_COLLECTION].find().sort("sort_order", 1)
        sections = [
            PolicySection(**doc).model_dump(by_alias=True)
            for doc in await cursor.to_list(length=20)
        ]
        return {"meta": meta, "sections": sections}

    async def upsert_meta(self, data: PolicyPageMetaUpdate) -> PolicyPageMeta:
        database = await db.get_database()
        collection = database[self.META_COLLECTION]
        payload = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        payload["updated_at"] = datetime.utcnow()
        payload["meta_key"] = META_KEY

        existing = await collection.find_one({"meta_key": META_KEY})
        if existing:
            await collection.update_one({"meta_key": META_KEY}, {"$set": payload})
            doc = await collection.find_one({"meta_key": META_KEY})
        else:
            payload.setdefault("active", True)
            for field in ("page_eyebrow", "page_title", "page_intro", "last_updated_label"):
                payload.setdefault(field, "")
            result = await collection.insert_one(payload)
            doc = await collection.find_one({"_id": result.inserted_id})

        await self._invalidate()
        return PolicyPageMeta(**doc)

    async def upsert_section_by_slug(
        self, slug: str, data: Dict[str, Any]
    ) -> PolicySection:
        database = await db.get_database()
        collection = database[self.SECTIONS_COLLECTION]
        payload = {**data, "slug": slug, "updated_at": datetime.utcnow()}

        existing = await collection.find_one({"slug": slug})
        if existing:
            await collection.update_one({"slug": slug}, {"$set": payload})
            doc = await collection.find_one({"slug": slug})
        else:
            payload.setdefault("title", "")
            payload.setdefault("body", "")
            payload.setdefault("sort_order", 0)
            payload.setdefault("active", True)
            result = await collection.insert_one(payload)
            doc = await collection.find_one({"_id": result.inserted_id})

        await self._invalidate()
        return PolicySection(**doc)

    async def create_section(self, data: PolicySectionCreate) -> PolicySection:
        database = await db.get_database()
        doc = data.model_dump()
        doc["updated_at"] = datetime.utcnow()
        result = await database[self.SECTIONS_COLLECTION].insert_one(doc)
        doc["_id"] = result.inserted_id
        await self._invalidate()
        return PolicySection(**doc)

    async def update_section(
        self, section_id: str, update_data: Dict[str, Any]
    ) -> Optional[PolicySection]:
        database = await db.get_database()
        update_data["updated_at"] = datetime.utcnow()
        result = await database[self.SECTIONS_COLLECTION].update_one(
            {"_id": ObjectId(section_id)},
            {"$set": update_data},
        )
        if result.modified_count > 0:
            await self._invalidate()
            doc = await database[self.SECTIONS_COLLECTION].find_one(
                {"_id": ObjectId(section_id)}
            )
            return PolicySection(**doc) if doc else None
        return None

    async def delete_section(self, section_id: str) -> bool:
        database = await db.get_database()
        result = await database[self.SECTIONS_COLLECTION].delete_one(
            {"_id": ObjectId(section_id)}
        )
        if result.deleted_count > 0:
            await self._invalidate()
        return result.deleted_count > 0
