# F-14 — Public Analytics Write Hardening

## Vulnerability
`analytics.trackEvent` and `analytics.trackMetric` are intentionally
**unauthenticated** CQRS operations (the storefront emits them from the browser
with no admin key — see `src/cqrs/router.py` `_authorize`, which explicitly
exempts these two operations).

Before this fix the request `params` flowed straight into
`AnalyticsEventCreate` / `AnalyticsMetricCreate`, which accepted:
- an **arbitrary `event_type`** (any string),
- an **arbitrary `metric_name` / `metric_type`**,
- an **unbounded numeric `value`** (including `NaN` / `Infinity`),
- an **unbounded `metadata` / `dimensions`** object.

## Root cause
No allowlist or bounds on a public write path. `AnalyticsService` uses the
client-supplied `event_type` (and `metric_name`) **directly as a Redis key** and,
for `event_type == "order_placed"`, does:

```python
revenue_key = f"...revenue:{date_str}"
await redis.incrbyfloat(revenue_key, float(metadata.get("amount", 0)))
```

So an anonymous attacker could:
1. **Poison the revenue dashboard** — `order_placed` with a huge
   `metadata.amount` inflates the public `revenue:<date>` counter.
2. **Explode the Redis key-space** — any `event_type` becomes a new
   `counter:<event_type>:<date>` key.
3. **Abuse storage** — unbounded `metadata`/`dimensions` documents persisted to
   Mongo.
4. **Corrupt metrics** — junk metric names or `NaN`/`Infinity` values.

(Per-IP throttling was previously bypassable via F-03 XFF spoofing — now fixed,
so the rate caps below are effective.)

## Fix
Two layers, both server-side:

### 1. Validation (allowlists + bounds) — `src/cqrs/param_models.py`
New typed param models, registered in `PARAM_MODELS` so `CQRSRouter._validate_params`
runs them **before** authorization or the mutation:

- `AnalyticsTrackEventParams`
  - `event_type` must be in `ALLOWED_EVENT_TYPES` (closed set covering every
    type the `AnalyticsService` actually handles).
  - `order_placed.metadata.amount` must be a finite number in `[0, 10_000_000]`.
  - `metadata` bounded: ≤ 20 keys, scalar values only (no nested objects/arrays),
    string values ≤ 256 chars, keys ≤ 64 chars.
  - `user_id` / `session_id` ≤ 128 chars, scalar only (rejects `{"$ne": null}`).
- `AnalyticsTrackMetricParams`
  - `metric_name` ∈ `ALLOWED_METRIC_NAMES`, `metric_type` ∈ `ALLOWED_METRIC_TYPES`.
  - `value` must be a finite number in `[-10_000_000, 10_000_000]` (rejects
    strings, `bool`, `NaN`, `Infinity`).
  - `dimensions` bounded identically to `metadata`.

Field names are kept snake_case (no camelCase aliases) so the validated
`model_dump(by_alias=True)` matches the downstream `AnalyticsEventCreate` /
`AnalyticsMetricCreate` field names. `extra="ignore"` strips unknown top-level
fields so they never reach Mongo (without rejecting benign storefront calls).

### 2. Per-IP volume cap — `config/rate_limits.yaml` + `rate_limit_config.py`
New `analytics_write` rule on `POST /` for operations `analytics.trackEvent` /
`analytics.trackMetric`: **120 req/min per IP, burst 30**. Because it is an
operation-specific rule it takes precedence over the generic
`public_post_fallback`. IP is derived from the trusted platform header (F-03), so
the cap can't be bypassed by rotating `X-Forwarded-For`.

## Modified / added files
- `src/cqrs/param_models.py` — `AnalyticsTrackEventParams`, `AnalyticsTrackMetricParams`,
  `ALLOWED_EVENT_TYPES`, `ALLOWED_METRIC_NAMES`, `ALLOWED_METRIC_TYPES`,
  `_validate_kv_map`; registered both ops in `PARAM_MODELS`.
- `config/rate_limits.yaml` — `analytics_write` rule.
- `src/plugins/rate_limit_config.py` — same rule in the env fallback.
- `__tests__/test_security_f14.py` — unit, regression, and security tests.

## Tests
`__tests__/test_security_f14.py` (22 tests): valid events/metrics pass; unknown
`event_type`/`metric_name`/`metric_type` rejected; operator-injection rejected;
`order_placed` amount type/range enforced; metadata key-count/size/nesting
bounds; `NaN`/`Infinity`/out-of-range/`bool` metric values rejected; the
`analytics_write` rate-limit rule matches and beats the fallback; allowlists
cover every event type the service handles.

## Migration & rollback
- **Migration:** none. No schema or data migration. The storefront already sends
  snake_case `event_type` / `metric_name` / `metric_type`, all of which are in the
  allowlists. If a legitimate new event type is added later, append it to
  `ALLOWED_EVENT_TYPES` (or `ALLOWED_METRIC_NAMES`).
- **Rollback:** remove the two entries from `PARAM_MODELS` and delete the
  `analytics_write` rate-limit rule. No state to revert.
