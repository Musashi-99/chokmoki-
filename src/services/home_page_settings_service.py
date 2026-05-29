from typing import Any, Dict, Optional
from datetime import datetime
import json
from src.database.connection import db
from src.models.home_page_settings import HomePageSettings, HomePageSettingsUpdate
from src.services.cache_service import cache
from src.utils.mongo_json import mongo_json_dumps
from src.plugins.logger import logger

MAIN_KEY = "main"
CACHE_KEY = "chokmoki:home_page"
CACHE_TTL = 600


class HomePageSettingsService:
    COLLECTION_NAME = "home_page_settings"

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

        result = HomePageSettings(**doc).model_dump(by_alias=True)
        await cache.set(CACHE_KEY, mongo_json_dumps(result), CACHE_TTL)
        return result

    async def get_admin(self) -> Optional[HomePageSettings]:
        database = await db.get_database()
        doc = await database[self.COLLECTION_NAME].find_one({"settings_key": MAIN_KEY})
        if doc:
            return HomePageSettings(**doc)
        return None

    async def upsert(self, data: HomePageSettingsUpdate) -> HomePageSettings:
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
            result = await collection.insert_one(payload)
            doc = await collection.find_one({"_id": result.inserted_id})

        await cache.delete(CACHE_KEY)
        logger.info("Home page settings upserted")
        return HomePageSettings(**doc)
