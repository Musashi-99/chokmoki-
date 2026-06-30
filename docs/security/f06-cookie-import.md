# F-06 — Cookie Import Fix

## Vulnerability

`Cookie` was used in `/api/admin/refresh` and `/api/admin/logout` without being imported from FastAPI, causing `NameError` at module import time and breaking the entire serverless function.

## Fix

Added `Cookie` to the FastAPI import in `api/index.py`.

## Tests

```bash
pytest __tests__/test_import_smoke.py -v
```

## Migration

None — no API or config changes.

## Rollback

Reverting the import line restores the crash; do not roll back without a replacement fix.

## Performance impact

None.

## Security impact

Restores admin session refresh and logout; no auth weakening.
