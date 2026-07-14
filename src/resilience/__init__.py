"""Cross-cutting resilience primitives for outbound calls to external
dependencies (Razorpay, Shiprocket, Telegram) — timeout, retry-with-backoff,
circuit breaker, bulkhead. Each concern is one small, independently testable
module; compose them at the call site rather than building a single
do-everything wrapper.
"""
