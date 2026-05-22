from typing import Any, Dict, Optional
from datetime import datetime
import json
from src.database.connection import db
from src.models.studio_settings import StudioSettings, StudioSettingsUpdate
from src.services.cache_service import cache
from src.utils.mongo_json import mongo_json_dumps
from src.plugins.logger import logger

MAIN_KEY = "main"
CACHE_KEY = "chokmoki:studio_settings"
CACHE_TTL = 600


class StudioSettingsService:
    COLLECTION_NAME = "studio_settings"

    async def get_public(self) -> Optional[Dict[str, Any]]:
        cached = await cache.get(CACHE_KEY)
        if cached:
            return json.loads(cached)

        database = await db.get_database()
        doc = await database[self.COLLECTION_NAME].find_one(
            {"settings_key": MAIN_KEY, "active": True}
        )
        if not doc:
            return None

        result = StudioSettings(**doc).model_dump(by_alias=True)
        await cache.set(CACHE_KEY, mongo_json_dumps(result), CACHE_TTL)
        return result

    async def get_admin(self) -> Optional[StudioSettings]:
        database = await db.get_database()
        doc = await database[self.COLLECTION_NAME].find_one({"settings_key": MAIN_KEY})
        if doc:
            return StudioSettings(**doc)
        return None

    async def upsert(self, data: StudioSettingsUpdate) -> StudioSettings:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]

        payload = data.model_dump(exclude_unset=True)
        payload["updated_at"] = datetime.utcnow()
        payload["settings_key"] = MAIN_KEY

        existing = await collection.find_one({"settings_key": MAIN_KEY})
        if existing:
            await collection.update_one({"settings_key": MAIN_KEY}, {"$set": payload})
            doc = await collection.find_one({"settings_key": MAIN_KEY})
        else:
            payload.setdefault("active", True)
            payload.setdefault("email", "")
            payload.setdefault("address", "")
            payload.setdefault("address_lines", [])
            payload.setdefault("address_detail", "")
            payload.setdefault("map_lat", 22.662833)
            payload.setdefault("map_lon", 88.429749)
            payload.setdefault("instagram_url", "")
            payload.setdefault("facebook_url", "")
            result = await collection.insert_one(payload)
            doc = await collection.find_one({"_id": result.inserted_id})

        await cache.delete(CACHE_KEY)
        logger.info("Studio settings upserted")
        return StudioSettings(**doc)
