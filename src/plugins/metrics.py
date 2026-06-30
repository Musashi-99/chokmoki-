from __future__ import annotations

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST


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


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST

