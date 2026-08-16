import os, sys, json
os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch
from src.plugins.structured_log import app_log


def test_app_log_emits_structured_json_with_correlation_id():
    with patch("src.plugins.structured_log.logger") as mock_logger:
        app_log(
            severity="INFO",
            module="order_service",
            event="order_created",
            correlation_id="req-abc123",
            order_id="chokmoki_order_1",
            total_amount=1999.0,
        )
        mock_logger.info.assert_called_once()
        emitted = json.loads(mock_logger.info.call_args.args[0])
        assert emitted["correlation_id"] == "req-abc123"
        assert emitted["event"] == "order_created"
        assert emitted["order_id"] == "chokmoki_order_1"
