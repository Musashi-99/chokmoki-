from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from src.config import settings
from src.plugins.rate_limit_utils import parse_time_to_seconds


@dataclass(frozen=True)
class RateLimitBucket:
    scope: str  # ip | email | admin | endpoint
    rate: int
    window: str
    burst: int
    field: Optional[str] = None  # JSON body field for email scope

    @property
    def window_seconds(self) -> int:
        return parse_time_to_seconds(self.window)

    @property
    def capacity(self) -> int:
        return max(self.burst, 1)

    @property
    def refill_per_ms(self) -> float:
        window_ms = self.window_seconds * 1000
        if window_ms <= 0:
            return 0.0
        return self.rate / window_ms


@dataclass(frozen=True)
class RateLimitRule:
    id: str
    methods: Sequence[str]
    paths: Sequence[str]
    operations: Sequence[str]
    buckets: Sequence[RateLimitBucket]
    enabled: bool = True


@dataclass
class ResolvedRateLimit:
    rule_id: str
    bucket: RateLimitBucket
    redis_key: str


SKIP_PATHS = frozenset(
    {
        "/health",
        "/health/live",
        "/health/ready",
    }
)

FALLBACK_RULE_IDS = frozenset({"public_get", "public_post_fallback"})

_LUA_PATH = Path(__file__).with_name("rate_limit_lua.lua")
_DEFAULT_YAML = Path(__file__).resolve().parents[2] / "config" / "rate_limits.yaml"


def _hash_identifier(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:32]


def load_rate_limit_rules() -> List[RateLimitRule]:
    config_path = settings.rate_limit_config_file or os.getenv("RATE_LIMIT_CONFIG_FILE")
    path = Path(config_path) if config_path else _DEFAULT_YAML
    if path.is_file():
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        return _parse_yaml_rules(raw)

    return _default_rules_from_env()


def _parse_bucket(raw: Dict[str, Any]) -> RateLimitBucket:
    return RateLimitBucket(
        scope=str(raw.get("scope", "ip")),
        rate=int(raw.get("rate", 1)),
        window=str(raw.get("window", "1m")),
        burst=int(raw.get("burst", raw.get("rate", 1))),
        field=raw.get("field"),
    )


def _parse_yaml_rules(raw: Dict[str, Any]) -> List[RateLimitRule]:
    rules: List[RateLimitRule] = []
    for item in raw.get("rules", []):
        if not item.get("enabled", True):
            continue
        match = item.get("match", {})
        buckets = [_parse_bucket(b) for b in item.get("buckets", [])]
        rules.append(
            RateLimitRule(
                id=str(item["id"]),
                methods=[m.upper() for m in match.get("methods", ["*"])],
                paths=list(match.get("paths", ["*"])),
                operations=list(match.get("operations", [])),
                buckets=buckets,
                enabled=True,
            )
        )
    return rules


def _default_rules_from_env() -> List[RateLimitRule]:
    """Built-in rules mirroring Phase 1 env vars when no YAML file is present."""
    return [
        RateLimitRule(
            id="admin_login_ip",
            methods=["POST"],
            paths=["/api/admin/login"],
            operations=[],
            buckets=[
                RateLimitBucket("ip", 5, "15m", 2),
                RateLimitBucket("email", 3, "15m", 1, field="email"),
            ],
        ),
        RateLimitRule(
            id="orders",
            methods=["POST"],
            paths=["/api/orders", "/"],
            operations=["order.create", "order.initiate"],
            buckets=[
                RateLimitBucket("ip", settings.rate_limit_order_max, settings.rate_limit_order_time, 2),
                RateLimitBucket("email", 3, settings.rate_limit_order_time, 2, field="userEmail"),
            ],
        ),
        RateLimitRule(
            id="coupon_preview",
            methods=["POST"],
            paths=["/api/coupons/preview"],
            operations=[],
            buckets=[RateLimitBucket("ip", 30, "1h", 10)],
        ),
        RateLimitRule(
            id="contact",
            methods=["POST"],
            paths=["/api/contact"],
            operations=["contact.create"],
            buckets=[
                RateLimitBucket("ip", settings.rate_limit_contact_max, settings.rate_limit_contact_time, 1),
                RateLimitBucket("email", 1, settings.rate_limit_contact_time, 1, field="email"),
            ],
        ),
        RateLimitRule(
            id="newsletter",
            methods=["POST"],
            paths=["/api/newsletter"],
            operations=["newsletter.subscribe"],
            buckets=[
                RateLimitBucket(
                    "ip",
                    settings.rate_limit_newsletter_max,
                    settings.rate_limit_newsletter_time,
                    1,
                ),
                RateLimitBucket(
                    "email",
                    1,
                    settings.rate_limit_newsletter_time,
                    1,
                    field="email",
                ),
            ],
        ),
        RateLimitRule(
            id="analytics_write",
            methods=["POST"],
            paths=["/"],
            operations=["analytics.trackEvent", "analytics.trackMetric"],
            buckets=[RateLimitBucket("ip", 120, "1m", 30)],
        ),
        RateLimitRule(
            id="product_search",
            methods=["GET"],
            paths=["/api/products"],
            operations=[],
            buckets=[RateLimitBucket("ip", 60, "1m", 20)],
        ),
        RateLimitRule(
            id="admin_api",
            methods=["*"],
            paths=["/api/admin/*"],
            operations=[],
            buckets=[
                RateLimitBucket("ip", 120, "1m", 30),
                RateLimitBucket("admin", 60, "1m", 30),
            ],
        ),
        RateLimitRule(
            id="admin_upload",
            methods=["POST"],
            paths=["/api/admin/upload"],
            operations=[],
            buckets=[
                RateLimitBucket("ip", 30, "1m", 10),
                RateLimitBucket("admin", 20, "1m", 5),
            ],
        ),
        RateLimitRule(
            id="webhook_razorpay",
            methods=["POST"],
            paths=["/webhook/razorpay"],
            operations=[],
            buckets=[RateLimitBucket("ip", 1000, "1m", 100)],
        ),
        RateLimitRule(
            id="public_get",
            methods=["GET"],
            paths=["*"],
            operations=[],
            buckets=[
                RateLimitBucket(
                    "ip",
                    settings.rate_limit_normal_get,
                    settings.rate_limit_normal_time,
                    settings.rate_limit_normal_get,
                ),
            ],
        ),
        RateLimitRule(
            id="public_post_fallback",
            methods=["POST"],
            paths=["*"],
            operations=[],
            buckets=[
                RateLimitBucket(
                    "ip",
                    settings.rate_limit_normal_post,
                    settings.rate_limit_normal_time,
                    settings.rate_limit_normal_post,
                ),
            ],
        ),
    ]


def read_lua_script() -> str:
    return _LUA_PATH.read_text(encoding="utf-8")


def _path_matches(rule_paths: Sequence[str], path: str) -> bool:
    for pattern in rule_paths:
        if pattern == "*":
            return True
        if pattern.endswith("*") and path.startswith(pattern[:-1]):
            return True
        if pattern == path:
            return True
    return False


def _method_matches(rule_methods: Sequence[str], method: str) -> bool:
    upper = method.upper()
    return "*" in rule_methods or upper in rule_methods


def match_rules(
    rules: Sequence[RateLimitRule],
    *,
    method: str,
    path: str,
    operation: Optional[str],
) -> List[RateLimitRule]:
    matched: List[RateLimitRule] = []
    for rule in rules:
        if not rule.enabled:
            continue
        if not _method_matches(rule.methods, method):
            continue
        if not _path_matches(rule.paths, path):
            continue
        if rule.operations and path == "/":
            if not operation or operation not in rule.operations:
                continue
        matched.append(rule)
    return matched


def build_redis_key(rule_id: str, bucket: RateLimitBucket, identifier: str) -> str:
    safe_id = re.sub(r"[^a-zA-Z0-9._-]", "_", identifier)[:128]
    return f"rl:{bucket.scope}:{rule_id}:{safe_id}"


def resolve_identifiers(
    *,
    scope: str,
    ip: str,
    path: str,
    admin_email: Optional[str],
    body_fields: Dict[str, Any],
    bucket: RateLimitBucket,
) -> Optional[str]:
    if scope == "ip":
        return ip if ip != "unknown" else None
    if scope == "endpoint":
        return f"{path}"
    if scope == "admin":
        return admin_email
    if scope == "email":
        field = bucket.field or "email"
        raw = body_fields.get(field) or body_fields.get(field.lower())
        if isinstance(raw, str) and raw.strip():
            return _hash_identifier(raw)
    return None


def resolve_rate_limits(
    rules: Sequence[RateLimitRule],
    *,
    method: str,
    path: str,
    operation: Optional[str],
    ip: str,
    admin_email: Optional[str],
    body_fields: Dict[str, Any],
) -> List[ResolvedRateLimit]:
    if path in SKIP_PATHS:
        return []

    resolved: List[ResolvedRateLimit] = []
    seen_keys: set[str] = set()

    matched_rules = match_rules(rules, method=method, path=path, operation=operation)
    has_specific = any(rule.id not in FALLBACK_RULE_IDS for rule in matched_rules)
    if has_specific:
        matched_rules = [rule for rule in matched_rules if rule.id not in FALLBACK_RULE_IDS]

    for rule in matched_rules:
        for bucket in rule.buckets:
            identifier = resolve_identifiers(
                scope=bucket.scope,
                ip=ip,
                path=path,
                admin_email=admin_email,
                body_fields=body_fields,
                bucket=bucket,
            )
            if not identifier:
                continue
            redis_key = build_redis_key(rule.id, bucket, identifier)
            if redis_key in seen_keys:
                continue
            seen_keys.add(redis_key)
            resolved.append(
                ResolvedRateLimit(rule_id=rule.id, bucket=bucket, redis_key=redis_key)
            )
    return resolved
