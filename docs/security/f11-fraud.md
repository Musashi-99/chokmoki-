# F-11 — Fraud Detection Engine

## Vulnerability
Fraud engine was disabled by default (`FRAUD_ENABLED=false`), short-circuiting to `ALLOW` for all orders.

## Changes
- `src/fraud/enrichment.py` — velocity, disposable email, Tor, duplicate order, device signals
- Expanded `config/fraud_rules.yaml` — YARA-style rules with hot reload
- `src/services/fraud_review_service.py` — manual review queue
- `GET /api/admin/fraud/reviews`, `POST /api/admin/fraud/reviews/{id}/resolve`
- Production requires `FRAUD_ENABLED=true`

## Production env
```env
FRAUD_ENABLED=true
FRAUD_FAIL_CLOSED=true
FRAUD_RULES_FILE=config/fraud_rules.yaml
```

## Migration
1. Set env vars in Vercel/platform secrets.
2. Monitor `fraud_decisions` and `fraud_review_queue` collections.
3. Tune thresholds in `fraud_rules.yaml` without redeploy (hot reload).

## Rollback
Set `FRAUD_ENABLED=false` in non-production only; production boot will fail if disabled.
