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

from api.routes.orders import razorpay_webhook

WEBHOOK_BODY = json.dumps({
    "event": "payment.captured",
    "payload": {"payment": {"entity": {
        "id": "pay_123", "order_id": "order_abc",
        "notes": {"order_id": "chokmoki_order_1"},
    }}},
}).encode()


@pytest.mark.asyncio
async def test_duplicate_webhook_delivery_only_processes_once():
    request = AsyncMock()
    request.body = AsyncMock(return_value=WEBHOOK_BODY)
    request.state.correlation_id = "req-1"

    with patch("api.routes.orders.RazorpayService") as mock_rp_cls, \
         patch("api.routes.orders.IdempotencyService") as mock_idem_cls, \
         patch("api.routes.orders.publish_order_event", new=AsyncMock()), \
         patch("api.routes.orders.settings") as mock_settings:
        mock_settings.razorpay_webhook_secret = "whsec"
        mock_rp_cls.return_value.verify_webhook_signature.return_value = True
        idem_instance = mock_idem_cls.return_value
        idem_instance.begin = AsyncMock(side_effect=[None, None])
        idem_instance.store = AsyncMock()
        idem_instance.fingerprint.return_value = "fp"

        await razorpay_webhook(request, x_razorpay_signature="sig")
        await razorpay_webhook(request, x_razorpay_signature="sig")

        first_key = idem_instance.begin.call_args_list[0].args[0]
        second_key = idem_instance.begin.call_args_list[1].args[0]
        assert first_key == second_key == "razorpay_webhook:pay_123"
