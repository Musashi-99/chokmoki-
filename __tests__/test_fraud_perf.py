from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.fraud.engine import FraudEngine
from src.fraud.rules import load_rules


@pytest.mark.performance
def test_fraud_engine_eval_under_2ms_p50_local():
    loaded = load_rules("config/fraud_rules.yaml")
    engine = FraudEngine(loaded.rule_set)
    ctx = {
        "request": {"ip": "1.2.3.4", "user_agent": "ua", "endpoint": "/api/orders"},
        "event": {"type": "order_create", "amount": 1000, "currency": "INR"},
        "user": {"email": "ok@example.com", "phone": "9999999999"},
        "shipping": {"country": "IN", "postal_code": "400001", "city": "Mumbai", "state": "MH"},
        "attributes": {},
    }

    # Warmup
    for _ in range(50):
        engine.evaluate(ctx=ctx)

    samples = []
    for _ in range(500):
        t0 = time.perf_counter()
        engine.evaluate(ctx=ctx)
        samples.append((time.perf_counter() - t0) * 1000.0)

    samples.sort()
    p50 = samples[len(samples) // 2]
    assert p50 < 2.0

