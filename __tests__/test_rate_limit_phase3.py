"""Phase 3 token bucket rate limiter tests."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.plugins.rate_limit_config import (
    RateLimitBucket,
    RateLimitRule,
    match_rules,
    resolve_rate_limits,
)
from src.plugins.rate_limit_utils import parse_time_to_seconds
from src.plugins.token_bucket import TokenBucketLimiter


class TestParseTime:
    def test_minutes(self):
        assert parse_time_to_seconds("15m") == 900


class TestRuleMatching:
    def test_orders_rest_path(self):
        rules = [
            RateLimitRule(
                id="orders",
                methods=["POST"],
                paths=["/api/orders", "/"],
                operations=["order.create"],
                buckets=[RateLimitBucket("ip", 5, "1h", 2)],
            )
        ]
        matched = match_rules(rules, method="POST", path="/api/orders", operation=None)
        assert len(matched) == 1

    def test_cqrs_requires_operation(self):
        rules = [
            RateLimitRule(
                id="orders",
                methods=["POST"],
                paths=["/"],
                operations=["order.create"],
                buckets=[RateLimitBucket("ip", 5, "1h", 2)],
            )
        ]
        assert not match_rules(rules, method="POST", path="/", operation="product.list")
        assert match_rules(rules, method="POST", path="/", operation="order.create")

    def test_fallback_skipped_when_specific_matches(self):
        rules = [
            RateLimitRule(
                id="orders",
                methods=["POST"],
                paths=["/api/orders"],
                operations=[],
                buckets=[RateLimitBucket("ip", 5, "1h", 2)],
            ),
            RateLimitRule(
                id="public_post_fallback",
                methods=["POST"],
                paths=["*"],
                operations=[],
                buckets=[RateLimitBucket("ip", 400, "3m", 400)],
            ),
        ]
        resolved = resolve_rate_limits(
            rules,
            method="POST",
            path="/api/orders",
            operation=None,
            ip="1.2.3.4",
            admin_email=None,
            body_fields={},
        )
        assert len(resolved) == 1
        assert resolved[0].rule_id == "orders"

    def test_coupon_preview_beats_fallback(self):
        from src.plugins.rate_limit_config import _default_rules_from_env

        resolved = resolve_rate_limits(
            _default_rules_from_env(),
            method="POST",
            path="/api/coupons/preview",
            operation=None,
            ip="203.0.113.9",
            admin_email=None,
            body_fields={},
        )
        rule_ids = {r.rule_id for r in resolved}
        assert "coupon_preview" in rule_ids
        assert "public_post_fallback" not in rule_ids


class TestTokenBucketLimiter:
    @pytest.mark.asyncio
    async def test_consume_allowed(self):
        limiter = TokenBucketLimiter()
        bucket = RateLimitBucket("ip", 5, "1h", 2)
        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha")
        mock_redis.evalsha = AsyncMock(return_value=[1, 0])

        with patch(
            "src.plugins.token_bucket.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            result = await limiter.consume("rl:ip:test:1.2.3.4", bucket)
            assert result.allowed is True

    @pytest.mark.asyncio
    async def test_consume_denied_returns_retry(self):
        limiter = TokenBucketLimiter()
        bucket = RateLimitBucket("ip", 5, "1h", 2)
        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha")
        mock_redis.evalsha = AsyncMock(return_value=[0, 5000])

        with patch(
            "src.plugins.token_bucket.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            result = await limiter.consume("rl:ip:test:1.2.3.4", bucket)
            assert result.allowed is False
            assert result.retry_after_ms == 5000
