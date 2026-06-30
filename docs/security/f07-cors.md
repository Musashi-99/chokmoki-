# F-07 — CORS Wildcard Removal

## Vulnerability

`vercel.json` applied `Access-Control-Allow-Origin: *` to every route, including `/api/admin/*` and the CQRS endpoint. Any website could trigger cross-origin requests from a victim's browser and read responses from credential-less endpoints. Combined with `Access-Control-Allow-Headers: Authorization`, this amplified data-exposure risks (F-01/F-02).

## Root cause

Platform-level CORS headers in `vercel.json` conflicted with the application's `CORSMiddleware` allowlist. The wildcard header won for browser CORS checks, bypassing application intent.

## Changes

- Removed the `headers` block from `vercel.json` (no platform CORS override)
- Added `src/security/cors_policy.py` for origin validation and middleware defaults
- Restricted allowed methods and headers (no `*` wildcards)
- Credentials enabled only when explicit origins are configured
- Boot-time validation rejects malformed origins in all environments
- Production continues to require explicit `CORS_ALLOWED_ORIGINS`

## Affected files

- `vercel.json`
- `src/security/cors_policy.py` (new)
- `src/config.py`
- `api/index.py`
- `__tests__/test_security_f07.py` (new)

## Production configuration

```env
CORS_ALLOWED_ORIGINS=https://your-store.com,https://admin.your-store.com
```

Include every browser origin that calls the API (storefront, admin dashboard, preview deploys).

## Migration

1. Deploy with explicit `CORS_ALLOWED_ORIGINS` set in Vercel/platform env (required in production).
2. Remove any reliance on `Access-Control-Allow-Origin: *` from CDN or reverse-proxy layers.
3. Verify storefront and admin dashboards after deploy with browser devtools → Network → preflight `OPTIONS` requests.

## Rollback

1. Re-add the `headers` block to `vercel.json` (not recommended — reopens F-07).
2. Revert `api/index.py` and `src/config.py` CORS changes.
3. Set `CORS_ALLOWED_ORIGINS=*` in development only.

## Security impact

- Eliminates cross-origin read access from arbitrary attacker origins
- Admin and CQRS routes no longer inherit platform wildcard CORS
- Credentials (cookies) only sent when origins are explicitly trusted

## Performance impact

- Preflight responses cached for 600 seconds (`max_age`)
- Negligible runtime overhead (validation at boot only)
