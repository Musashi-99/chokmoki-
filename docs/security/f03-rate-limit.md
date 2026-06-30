# F-03 — Trusted Proxy & Rate Limit Hardening

## Changes

- Secure client IP via `x-vercel-forwarded-for` on Vercel; raw `X-Forwarded-For` ignored unless explicitly trusted
- Auth routes (`/api/admin/login`, `/refresh`, `/logout`) fail closed when Redis is unavailable
- Redis-backed login lockout after repeated failures (IP + email)
- Stricter admin login token bucket limits

## Environment

```env
RATE_LIMIT_AUTH_FAIL_CLOSED=true
RATE_LIMIT_FAIL_CLOSED=false
TRUSTED_PROXY_ENABLED=false
TRUST_X_FORWARDED_FOR=false
RATE_LIMIT_IP_HEADER=

LOGIN_MAX_FAILED_ATTEMPTS=5
LOGIN_LOCKOUT_SECONDS=1800
LOGIN_FAILURE_WINDOW_SECONDS=900
```

## Docker / nginx

Set `TRUSTED_PROXY_ENABLED=true` and terminate TLS at the proxy. Do **not** enable `TRUST_X_FORWARDED_FOR` in production.

## Vercel

No extra config — `VERCEL=1` enables `x-vercel-forwarded-for` automatically.

## Migration

Deploy with `RATE_LIMIT_AUTH_FAIL_CLOSED=true` (default). No API changes.

## Rollback

Revert commit; set `RATE_LIMIT_AUTH_FAIL_CLOSED=false` only if Redis SLO requires fail-open (not recommended).

## Tests

```bash
pytest __tests__/test_security_f03.py __tests__/test_rate_limit_phase3.py -v
```
