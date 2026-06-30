"""F-14 — Public analytics write hardening.

Vulnerability: `analytics.trackEvent` / `analytics.trackMetric` are public (the
storefront sends them without auth). Before this fix the create models accepted
an arbitrary `event_type` / `metric_name`, unbounded numeric `value`, and an
unbounded `metadata` / `dimensions` dict. An anonymous attacker could:
  * inflate the public `revenue:<date>` Redis counter via
    `event_type="order_placed"` with a huge `metadata.amount`;
  * explode the Redis key-space with arbitrary `event_type` counter keys;
  * persist unbounded documents (storage abuse);
  * poison dashboards with junk metric names / NaN / Infinity values.

These tests assert the CQRS param-model allowlists + bounds (unit/regression)
and the per-IP analytics rate-limit rule (security).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cqrs.param_models import (
    ALLOWED_EVENT_TYPES,
    ALLOWED_METRIC_NAMES,
    AnalyticsTrackEventParams,
    AnalyticsTrackMetricParams,
)
from src.cqrs.router import CQRSRouter
from src.plugins.rate_limit_config import (
    _default_rules_from_env,
    match_rules,
    resolve_rate_limits,
)


# --------------------------------------------------------------------------- #
# Unit — trackEvent validation
# --------------------------------------------------------------------------- #
class TestTrackEventValidation:
    def test_valid_event_passes(self):
        params = CQRSRouter._validate_params(
            "analytics.trackEvent",
            {"event_type": "product_view", "metadata": {"product_id": "abc"}},
        )
        assert params["event_type"] == "product_view"
        assert params["metadata"] == {"product_id": "abc"}
        # downstream AnalyticsEventCreate keys are present in snake_case
        assert "user_id" in params and "session_id" in params

    def test_unknown_event_type_rejected(self):
        with pytest.raises(ValueError, match="Invalid request parameters"):
            CQRSRouter._validate_params(
                "analytics.trackEvent",
                {"event_type": "evil_keyspace_pollution_$RANDOM"},
            )

    def test_operator_injection_event_type_rejected(self):
        with pytest.raises(ValueError, match="Invalid request parameters"):
            CQRSRouter._validate_params(
                "analytics.trackEvent",
                {"event_type": {"$ne": None}},
            )

    def test_order_placed_requires_numeric_amount(self):
        with pytest.raises(ValueError):
            AnalyticsTrackEventParams.model_validate(
                {"event_type": "order_placed", "metadata": {"amount": "9999999999"}}
            )

    def test_order_placed_amount_out_of_range_rejected(self):
        with pytest.raises(ValueError):
            AnalyticsTrackEventParams.model_validate(
                {"event_type": "order_placed", "metadata": {"amount": 9_999_999_999}}
            )

    def test_order_placed_negative_amount_rejected(self):
        with pytest.raises(ValueError):
            AnalyticsTrackEventParams.model_validate(
                {"event_type": "order_placed", "metadata": {"amount": -50}}
            )

    def test_order_placed_reasonable_amount_ok(self):
        model = AnalyticsTrackEventParams.model_validate(
            {"event_type": "order_placed", "metadata": {"amount": 4999.0}}
        )
        assert model.metadata["amount"] == 4999.0

    def test_metadata_too_many_keys_rejected(self):
        with pytest.raises(ValueError):
            AnalyticsTrackEventParams.model_validate(
                {
                    "event_type": "page_view",
                    "metadata": {f"k{i}": i for i in range(50)},
                }
            )

    def test_metadata_oversized_value_rejected(self):
        with pytest.raises(ValueError):
            AnalyticsTrackEventParams.model_validate(
                {"event_type": "page_view", "metadata": {"blob": "x" * 5000}}
            )

    def test_metadata_nested_object_rejected(self):
        with pytest.raises(ValueError):
            AnalyticsTrackEventParams.model_validate(
                {"event_type": "page_view", "metadata": {"nested": {"a": 1}}}
            )

    def test_overlong_user_id_rejected(self):
        with pytest.raises(ValueError):
            AnalyticsTrackEventParams.model_validate(
                {"event_type": "page_view", "user_id": "u" * 500}
            )


# --------------------------------------------------------------------------- #
# Unit — trackMetric validation
# --------------------------------------------------------------------------- #
class TestTrackMetricValidation:
    def test_valid_metric_passes(self):
        params = CQRSRouter._validate_params(
            "analytics.trackMetric",
            {"metric_name": "lcp_ms", "metric_type": "timing", "value": 1234.5},
        )
        assert params["metric_name"] == "lcp_ms"
        assert params["value"] == 1234.5

    def test_unknown_metric_name_rejected(self):
        with pytest.raises(ValueError, match="Invalid request parameters"):
            CQRSRouter._validate_params(
                "analytics.trackMetric",
                {"metric_name": "revenue", "metric_type": "counter", "value": 1},
            )

    def test_unknown_metric_type_rejected(self):
        with pytest.raises(ValueError):
            AnalyticsTrackMetricParams.model_validate(
                {"metric_name": "lcp_ms", "metric_type": "wat", "value": 1}
            )

    def test_non_numeric_value_rejected(self):
        with pytest.raises(ValueError):
            AnalyticsTrackMetricParams.model_validate(
                {"metric_name": "lcp_ms", "metric_type": "gauge", "value": "1e9"}
            )

    def test_infinite_value_rejected(self):
        with pytest.raises(ValueError):
            AnalyticsTrackMetricParams.model_validate(
                {"metric_name": "lcp_ms", "metric_type": "gauge", "value": float("inf")}
            )

    def test_value_out_of_range_rejected(self):
        with pytest.raises(ValueError):
            AnalyticsTrackMetricParams.model_validate(
                {"metric_name": "lcp_ms", "metric_type": "gauge", "value": 1e12}
            )

    def test_bool_value_rejected(self):
        with pytest.raises(ValueError):
            AnalyticsTrackMetricParams.model_validate(
                {"metric_name": "lcp_ms", "metric_type": "gauge", "value": True}
            )


# --------------------------------------------------------------------------- #
# Security — per-IP analytics rate limiting
# --------------------------------------------------------------------------- #
class TestAnalyticsRateLimit:
    def test_analytics_rule_matches_track_event(self):
        rules = _default_rules_from_env()
        matched = match_rules(
            rules, method="POST", path="/", operation="analytics.trackEvent"
        )
        assert any(r.id == "analytics_write" for r in matched)

    def test_analytics_specific_rule_beats_fallback(self):
        rules = _default_rules_from_env()
        resolved = resolve_rate_limits(
            rules,
            method="POST",
            path="/",
            operation="analytics.trackMetric",
            ip="203.0.113.9",
            admin_email=None,
            body_fields={},
        )
        rule_ids = {r.rule_id for r in resolved}
        assert "analytics_write" in rule_ids
        assert "public_post_fallback" not in rule_ids


# --------------------------------------------------------------------------- #
# Regression — allowlists cover what the AnalyticsService actually handles
# --------------------------------------------------------------------------- #
class TestAllowlistsCoverService:
    def test_service_handled_event_types_allowed(self):
        for event_type in ("product_view", "search", "add_to_cart", "order_placed"):
            assert event_type in ALLOWED_EVENT_TYPES

    def test_metric_names_non_empty(self):
        assert len(ALLOWED_METRIC_NAMES) > 0
