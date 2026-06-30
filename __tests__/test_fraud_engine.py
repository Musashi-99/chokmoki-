from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.fraud.engine import FraudEngine
from src.fraud.models import FraudAction
from src.fraud.rules import RuleSet, load_rules


class TestFraudEngine:
    def test_ruleset_loads_and_matches_disposable_email(self):
        loaded = load_rules("config/fraud_rules.yaml")
        engine = FraudEngine(loaded.rule_set)

        ctx = {
            "request": {"ip": "1.2.3.4", "user_agent": "ua", "endpoint": "/api/orders"},
            "event": {"type": "order_create", "amount": 1000, "currency": "INR"},
            "user": {"email": "a@mailinator.com", "phone": "9999999999"},
            "shipping": {"country": "IN", "postal_code": "400001", "city": "Mumbai", "state": "MH"},
            "attributes": {},
        }

        result = engine.evaluate(ctx=ctx)
        assert result.decision.action in {
            FraudAction.MANUAL_REVIEW,
            FraudAction.CHALLENGE,
            FraudAction.REJECT,
        }
        assert any(m.rule_id == "email_disposable_domain" for m in result.decision.matched)

    def test_no_matches_allows(self):
        rs = RuleSet(
            id="t",
            version="1",
            groups=[],
            rules=[],
        )
        engine = FraudEngine(rs)
        result = engine.evaluate(ctx={"user": {"email": "ok@x.com"}})
        assert result.decision.action == FraudAction.ALLOW
        assert result.decision.risk_score == 0

