# Phase 1 — Critical Security Hardening

## Changes

| Finding | Fix | Files |
|---------|-----|-------|
| C1/C2 CQRS IDOR | `order.get` requires admin JWT or matching `userEmail`; `order.getLog` and `order.updateStatus` require admin | `src/cqrs/router.py` |
| C3 Default secrets | Production boot fails on default `ADMIN_PASSWORD`, `JWT_SECRET`, missing `CRON_SECRET`, wildcard CORS | `src/config.py` |
| H2 REST rate limits | `POST /api/orders`, `/api/contact`, `/api/newsletter` rate-limited with `Retry-After` | `src/plugins/rate_limit.py` |
| H3 Cron auth | `X-Cron-Secret` header required when `CRON_SECRET` is set; mandatory in production | `api/index.py` |
| H4 Health disclosure | `/health` and `/health/live` are public liveness only; `/health/ready` for probes; `/health/detail` is admin-only | `api/index.py` |
| H5 CORS | Explicit `CORS_ALLOWED_ORIGINS`; `credentials` disabled when using `*` | `api/index.py`, `src/config.py` |
| H7 Quantity bounds | `quantity >= 1` in model; service enforces `ORDER_MIN_QUANTITY` / `ORDER_MAX_QUANTITY` | `src/models/order.py`, `src/services/order_service.py` |
| M1 Payment amount | Razorpay captured amount verified before completing pending orders | `src/services/razorpay_service.py`, `src/services/order_service.py` |
| M2 Regex ReDoS | User search input escaped before `$regex` | `src/utils/regex_safe.py`, product/order services |

## Environment Variables

```env
ENVIRONMENT=production
CORS_ALLOWED_ORIGINS=https://your-store.com
CRON_SECRET=<min 16 chars>
JWT_SECRET=<min 32 chars random>
ADMIN_PASSWORD=<strong password>
ORDER_MIN_QUANTITY=1
ORDER_MAX_QUANTITY=99
RATE_LIMIT_ORDER_MAX=5
RATE_LIMIT_CONTACT_MAX=3
RATE_LIMIT_NEWSLETTER_MAX=3
RATE_LIMIT_FAIL_CLOSED=false
```

## Rollback

Revert the Phase 1 commit. Set `ENVIRONMENT=development` to bypass production guards during rollback testing.

## Tests

```bash
pip install pytest pytest-asyncio httpx
pytest __tests__/test_security_phase1.py -v
```

## Vercel Cron

Add header to cron job:

```
X-Cron-Secret: <value of CRON_SECRET>
```
