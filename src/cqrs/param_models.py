"""Typed CQRS parameter models — reject operator injection before Mongo queries."""

from __future__ import annotations

import math
from typing import Any, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


def _reject_non_scalar(value: Any, field_name: str) -> Any:
    if value is None:
        return value
    if isinstance(value, (dict, list)):
        raise ValueError(f"{field_name} must be a string")
    return value


class OrderListParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=1000)
    user_email: Optional[EmailStr] = Field(default=None, alias="userEmail")
    status: Optional[str] = Field(default=None, max_length=64)
    search: Optional[str] = Field(default=None, max_length=256)
    from_date: Optional[str] = Field(default=None, alias="fromDate", max_length=32)
    to_date: Optional[str] = Field(default=None, alias="toDate", max_length=32)
    sort_order: int = Field(default=-1, alias="sortOrder")

    @field_validator("status", "search", "from_date", "to_date", mode="before")
    @classmethod
    def scalar_strings(cls, value: Any, info) -> Any:
        return _reject_non_scalar(value, info.field_name)

    @field_validator("skip", "limit", "sort_order", mode="before")
    @classmethod
    def scalar_ints(cls, value: Any, info) -> Any:
        return _reject_non_scalar(value, info.field_name)


class OrderGetParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., min_length=1, max_length=128)
    user_email: Optional[EmailStr] = Field(default=None, alias="userEmail")

    @field_validator("id", mode="before")
    @classmethod
    def id_must_be_string(cls, value: Any) -> Any:
        return _reject_non_scalar(value, "id")


class OrderLogParams(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=128)

    @field_validator("order_id", mode="before")
    @classmethod
    def order_id_must_be_string(cls, value: Any) -> Any:
        return _reject_non_scalar(value, "order_id")


class ShippingAddressListParams(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def email_must_be_string(cls, value: Any) -> Any:
        return _reject_non_scalar(value, "email")


class ShippingAddressGetParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., min_length=1, max_length=128)
    email: EmailStr

    @field_validator("id", "email", mode="before")
    @classmethod
    def scalar_fields(cls, value: Any, info) -> Any:
        return _reject_non_scalar(value, info.field_name)


class ShippingAddressMutationParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: Optional[str] = Field(default=None, max_length=128)
    email: EmailStr

    @field_validator("id", "email", mode="before")
    @classmethod
    def scalar_fields(cls, value: Any, info) -> Any:
        if value is None:
            return value
        return _reject_non_scalar(value, info.field_name)


# --- F-14: public analytics write hardening -------------------------------
# `analytics.trackEvent` / `analytics.trackMetric` are intentionally public
# (storefront sends them with no auth). Without validation an anonymous caller
# can poison dashboards (e.g. event_type="order_placed" with a huge
# metadata.amount drives the public `revenue:<date>` Redis counter), explode the
# Redis key-space with arbitrary event_type values, or store unbounded payloads.
# These models allowlist the names and bound every field BEFORE the mutation or
# the AnalyticsService ever sees the data.

#: Event types the storefront/analytics pipeline actually understands. Anything
#: else is rejected so it can never become an unbounded Redis counter key.
ALLOWED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "page_view",
        "product_view",
        "search",
        "add_to_cart",
        "remove_from_cart",
        "checkout_start",
        "checkout_complete",
        "order_placed",
        "wishlist_add",
        "wishlist_remove",
        "newsletter_signup",
        "contact_submit",
    }
)

ALLOWED_METRIC_NAMES: frozenset[str] = frozenset(
    {
        "page_load_ms",
        "api_latency_ms",
        "lcp_ms",
        "cls",
        "fid_ms",
        "ttfb_ms",
        "conversion_rate",
        "cart_value",
    }
)

ALLOWED_METRIC_TYPES: frozenset[str] = frozenset({"counter", "gauge", "histogram", "timing"})

_MAX_METADATA_KEYS = 20
_MAX_METADATA_VALUE_LEN = 256
_MAX_METADATA_KEY_LEN = 64
#: Upper bound for any single revenue/value contribution, to blunt poisoning.
_MAX_NUMERIC_VALUE = 10_000_000.0
_MIN_NUMERIC_VALUE = -10_000_000.0


def _validate_kv_map(value: Any, field_name: str) -> dict:
    """Bound an attacker-supplied metadata/dimensions map to scalar values."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    if len(value) > _MAX_METADATA_KEYS:
        raise ValueError(f"{field_name} has too many keys")
    cleaned: dict = {}
    for key, item in value.items():
        if not isinstance(key, str) or len(key) > _MAX_METADATA_KEY_LEN:
            raise ValueError(f"{field_name} key is invalid")
        if isinstance(item, bool) or isinstance(item, (int, float)):
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError(f"{field_name}.{key} must be a finite number")
            cleaned[key] = item
        elif isinstance(item, str):
            if len(item) > _MAX_METADATA_VALUE_LEN:
                raise ValueError(f"{field_name}.{key} is too long")
            cleaned[key] = item
        elif item is None:
            cleaned[key] = None
        else:
            raise ValueError(f"{field_name}.{key} must be a scalar value")
    return cleaned


class AnalyticsTrackEventParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    event_type: str = Field(..., min_length=1, max_length=64)
    timestamp: Optional[str] = Field(default=None, max_length=64)
    user_id: Optional[str] = Field(default=None, max_length=128)
    session_id: Optional[str] = Field(default=None, max_length=128)
    metadata: dict = Field(default_factory=dict)

    @field_validator("event_type", mode="before")
    @classmethod
    def event_type_allowed(cls, value: Any) -> Any:
        value = _reject_non_scalar(value, "event_type")
        if value not in ALLOWED_EVENT_TYPES:
            raise ValueError("Unsupported event_type")
        return value

    @field_validator("timestamp", "user_id", "session_id", mode="before")
    @classmethod
    def scalar_optional(cls, value: Any, info) -> Any:
        if value is None:
            return value
        return _reject_non_scalar(value, info.field_name)

    @field_validator("metadata", mode="before")
    @classmethod
    def bound_metadata(cls, value: Any) -> Any:
        return _validate_kv_map(value, "metadata")

    @model_validator(mode="after")
    def bound_revenue(self) -> "AnalyticsTrackEventParams":
        # order_placed.amount feeds the public revenue counter — clamp it hard.
        if self.event_type == "order_placed":
            amount = self.metadata.get("amount", 0)
            if isinstance(amount, bool) or not isinstance(amount, (int, float)):
                raise ValueError("order_placed metadata.amount must be a number")
            if not (0 <= float(amount) <= _MAX_NUMERIC_VALUE):
                raise ValueError("order_placed metadata.amount out of range")
        return self


class AnalyticsTrackMetricParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    metric_name: str = Field(..., min_length=1, max_length=64)
    metric_type: str = Field(..., min_length=1, max_length=32)
    value: float
    timestamp: Optional[str] = Field(default=None, max_length=64)
    dimensions: dict = Field(default_factory=dict)

    @field_validator("metric_name", mode="before")
    @classmethod
    def metric_name_allowed(cls, value: Any) -> Any:
        value = _reject_non_scalar(value, "metric_name")
        if value not in ALLOWED_METRIC_NAMES:
            raise ValueError("Unsupported metric_name")
        return value

    @field_validator("metric_type", mode="before")
    @classmethod
    def metric_type_allowed(cls, value: Any) -> Any:
        value = _reject_non_scalar(value, "metric_type")
        if value not in ALLOWED_METRIC_TYPES:
            raise ValueError("Unsupported metric_type")
        return value

    @field_validator("timestamp", mode="before")
    @classmethod
    def scalar_timestamp(cls, value: Any) -> Any:
        if value is None:
            return value
        return _reject_non_scalar(value, "timestamp")

    @field_validator("value", mode="before")
    @classmethod
    def bound_value(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("value must be a number")
        if not math.isfinite(float(value)):
            raise ValueError("value must be finite")
        if not (_MIN_NUMERIC_VALUE <= float(value) <= _MAX_NUMERIC_VALUE):
            raise ValueError("value out of range")
        return value

    @field_validator("dimensions", mode="before")
    @classmethod
    def bound_dimensions(cls, value: Any) -> Any:
        return _validate_kv_map(value, "dimensions")


PARAM_MODELS: dict[str, type[BaseModel]] = {
    "analytics.trackEvent": AnalyticsTrackEventParams,
    "analytics.trackMetric": AnalyticsTrackMetricParams,
    "order.list": OrderListParams,
    "order.get": OrderGetParams,
    "order.getLog": OrderLogParams,
    "shippingAddress.list": ShippingAddressListParams,
    "shippingAddress.get": ShippingAddressGetParams,
    "shippingAddress.update": ShippingAddressMutationParams,
    "shippingAddress.delete": ShippingAddressMutationParams,
}
