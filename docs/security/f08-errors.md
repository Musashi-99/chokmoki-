# F-08 — Error Disclosure Hardening

## Vulnerability

API endpoints returned raw exception strings (`str(e)`) to clients, including MongoDB errors, stack context, and internal validation messages. This aids reconnaissance (OWASP A05/A04, CWE-209).

## Root cause

Broad `except Exception` blocks re-raised `HTTPException` with interpolated exception text. CQRS param validation forwarded Pydantic internal messages.

## Changes

- `src/security/error_handling.py` — sanitization, correlation IDs, global exception handlers
- `src/middleware/correlation_id.py` — `X-Request-Id` on every request/response
- `api/index.py` — registered handlers; removed verbose 500 `detail` strings
- `src/cqrs/router.py` — generic validation failure message

## Client error shape

```json
{
  "detail": "An internal error occurred.",
  "correlation_id": "a1b2c3d4e5f6..."
}
```

Clients may send `X-Request-Id` to correlate support requests. Safe business messages (e.g. `Order not found`, auth failures) are still returned for 4xx responses.

## Migration

1. Deploy — no env changes required.
2. Update frontends to read `correlation_id` from error JSON and optionally send `X-Request-Id` on requests.
3. Support staff search logs by `correlation_id`.

## Rollback

1. Remove `register_exception_handlers` and `CorrelationIdMiddleware` from `api/index.py`.
2. Revert `src/cqrs/router.py` validation message change.

## Security impact

- Internal paths, driver errors, and stack details no longer exposed to clients
- Operators can trace failures via correlation ID in server logs

## Performance impact

- One UUID per request; negligible overhead
- Exception logging unchanged except for correlation ID field
