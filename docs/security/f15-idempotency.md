# F-15 — Order Idempotency

## Vulnerability
COD order creation used a fresh server UUID per request with no client idempotency key, so network retries created duplicate orders.

## Changes
- `src/security/idempotency.py` — Redis-backed keys with request fingerprinting
- `POST /api/orders` requires `Idempotency-Key` header in production
- CQRS order mutations accept `idempotencyKey` on `APIRequest`
- Production requires `IDEMPOTENCY_ENABLED=true`

## Client usage
```http
POST /api/orders
Idempotency-Key: 7f3c2a1b-unique-per-attempt
```

Replays with the same key and body return the cached response. Mismatched body returns `409`.

## Migration
Update storefront to generate and persist `Idempotency-Key` per checkout attempt until success.

## Rollback
Set `IDEMPOTENCY_REQUIRED_IN_PRODUCTION=false` and `IDEMPOTENCY_ENABLED=false` (non-production only).
