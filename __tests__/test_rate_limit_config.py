import os, sys
os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.plugins.rate_limit_config import load_rate_limit_rules, match_rules


def test_otp_verify_has_a_dedicated_identifier_scoped_rule():
    rules = load_rate_limit_rules()
    matched = match_rules(rules, method="POST", path="/api/auth/otp/verify", operation=None)
    matched_ids = [r.id for r in matched]
    assert "otp_verify" in matched_ids
    rule = next(r for r in matched if r.id == "otp_verify")
    scopes = {b.scope for b in rule.buckets}
    assert "email" in scopes


def test_coupon_preview_has_a_dedicated_rule():
    rules = load_rate_limit_rules()
    matched = match_rules(rules, method="POST", path="/api/coupons/preview", operation=None)
    assert "coupons_preview" in [r.id for r in matched]
