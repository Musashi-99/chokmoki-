from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST


FRAUD_EVAL_TOTAL = Counter(
    "fraud_eval_total",
    "Total fraud evaluations",
    ["action", "rule_set_id", "rule_set_version"],
)

FRAUD_EVAL_LATENCY_MS = Histogram(
    "fraud_eval_latency_ms",
    "Fraud evaluation latency in milliseconds",
    buckets=(1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000),
)

# Outbound calls to external dependencies (Razorpay, Shiprocket, Telegram),
# recorded once at src/resilience/guarded.py's single composition point —
# every guarded call gets counted automatically, nothing per-service to add.
DEPENDENCY_CALL_TOTAL = Counter(
    "dependency_call_total",
    "Outbound calls to external dependencies, by outcome",
    ["dependency", "outcome"],  # outcome: success | failure | timeout | breaker_open
)

DEPENDENCY_CALL_LATENCY_MS = Histogram(
    "dependency_call_latency_ms",
    "Outbound dependency call latency in milliseconds",
    ["dependency"],
    buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 20000),
)

# Set on trip/reset transitions inside src/resilience/circuit_breaker.py —
# a per-process snapshot of what that process has observed, not a live poll
# of the (Redis-backed, cross-process) authoritative state, so two processes
# can transiently disagree until each next observes the other's transition.
CIRCUIT_BREAKER_OPEN = Gauge(
    "circuit_breaker_open",
    "1 if this process last observed the named circuit breaker as open, 0 if closed",
    ["name"],
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests handled",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_LATENCY_MS = Histogram(
    "http_request_latency_ms",
    "HTTP request latency in milliseconds",
    ["method", "path"],
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST

