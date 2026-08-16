import os, sys
os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.routes.admin_content import admin_upsert_home_page

@pytest.mark.asyncio
async def test_home_page_update_invalidates_public_cache():
    with patch("api.routes.admin_content.cache") as mock_cache, \
         patch("api.routes.admin_content.HomePageSettingsService") as mock_service_cls:
        mock_cache.delete = AsyncMock()
        instance = mock_service_cls.return_value
        instance.upsert = AsyncMock(return_value=MagicMock(model_dump=lambda **_: {}))
        await admin_upsert_home_page(payload={}, email="admin@chokmoki.test")
        mock_cache.delete.assert_awaited_once_with("chokmoki:home-page")
