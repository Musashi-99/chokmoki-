import os
import sys

os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import AsyncMock, patch
from bson import ObjectId

from src.models.account_page_settings import AccountPageSettings, AccountPageSettingsUpdate
from src.services.account_page_settings_service import AccountPageSettingsService


def test_account_page_defaults_include_three_slides_and_timing():
    settings = AccountPageSettings()
    assert settings.slide_1_title == "Sterling silver, made to last."
    assert settings.slide_2_title == "Jewellery for every day."
    assert settings.slide_3_title == "Crafted for a lifetime."
    assert settings.interval_ms == 5000
    assert settings.fade_ms == 400


def test_update_model_accepts_partial_slide_fields():
    data = AccountPageSettingsUpdate(slide_2_title="New line.", interval_ms=4500)
    dumped = data.model_dump(exclude_unset=True)
    assert dumped == {"slide_2_title": "New line.", "interval_ms": 4500}


def _db(col):
    return AsyncMock(return_value={"account_page_settings": col})


@pytest.mark.asyncio
async def test_get_public_returns_none_when_missing():
    col = AsyncMock()
    col.find_one = AsyncMock(return_value=None)
    with patch("src.services.account_page_settings_service.db.get_database", new=_db(col)), patch(
        "src.services.account_page_settings_service.cache.get", new=AsyncMock(return_value=None)
    ):
        assert await AccountPageSettingsService().get_public() is None


@pytest.mark.asyncio
async def test_upsert_then_public_returns_slides():
    oid = ObjectId()
    stored = {}

    async def find_one(query):
        if stored.get("doc"):
            return stored["doc"]
        return None

    async def insert_one(payload):
        stored["doc"] = {**payload, "_id": oid, "active": payload.get("active", True)}
        return type("R", (), {"inserted_id": oid})()

    async def update_one(_query, update):
        stored["doc"] = {**stored.get("doc", {}), **update["$set"]}
        return None

    col = AsyncMock()
    col.find_one = find_one
    col.insert_one = insert_one
    col.update_one = update_one

    with patch("src.services.account_page_settings_service.db.get_database", new=_db(col)), patch(
        "src.services.account_page_settings_service.cache.get", new=AsyncMock(return_value=None)
    ), patch(
        "src.services.account_page_settings_service.cache.set", new=AsyncMock()
    ), patch(
        "src.services.account_page_settings_service.cache.delete", new=AsyncMock()
    ):
        service = AccountPageSettingsService()
        await service.upsert(
            AccountPageSettingsUpdate(
                slide_1_kicker="Since 1955",
                slide_1_title="Sterling silver, made to last.",
                slide_1_body="Hallmarked 92.5.",
                interval_ms=3000,
                fade_ms=400,
            )
        )
        public = await service.get_public()
        assert public["slide_1_title"] == "Sterling silver, made to last."
        assert public["interval_ms"] == 3000
        assert public["fade_ms"] == 400
