import os, sys
os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pytest
from unittest.mock import AsyncMock, patch

from api.routes.storefront import api_get_hero_config, api_list_faq

@pytest.mark.asyncio
async def test_hero_config_reads_from_cache_when_present():
    cached_payload = {"media_type": "image", "media_url": "https://x/y.jpg", "alt_text": "hero", "active": True}
    with patch("api.routes.storefront.cache") as mock_cache, \
         patch("api.routes.storefront.HeroConfigService") as mock_service_cls:
        mock_cache.get = AsyncMock(return_value=json.dumps(cached_payload))
        response = await api_get_hero_config()
        mock_service_cls.assert_not_called()
        assert json.loads(response.body) == cached_payload

@pytest.mark.asyncio
async def test_faq_list_writes_through_to_cache_on_miss():
    with patch("api.routes.storefront.cache") as mock_cache, \
         patch("api.routes.storefront.FAQItemService") as mock_service_cls:
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()
        instance = mock_service_cls.return_value
        instance.list = AsyncMock(return_value=[{"question": "Q", "answer": "A", "scope": "general"}])
        await api_list_faq(scope=None)
        mock_cache.set.assert_awaited_once()
        args, _ = mock_cache.set.call_args
        assert args[0] == "chokmoki:faq:all"
