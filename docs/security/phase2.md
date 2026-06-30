# Phase 2 — Authentication & Authorization

## Features

- Short-lived access JWT (default 60m) with `jti` + Redis session binding
- Rotating refresh tokens (default 7d) in httpOnly cookie
- JWT revocation via Redis `admin:revoked:{jti}`
- httpOnly secure cookies + CSRF double-submit (`chokmoki_csrf` / `X-CSRF-Token`)
- Optional TOTP MFA (`ADMIN_MFA_SECRET`)
- RBAC permission helpers (`require_permission`)
- Admin audit middleware for mutating `/api/admin/*` routes
- Legacy Bearer token in login JSON disabled by default (`ADMIN_LEGACY_BEARER_ENABLED=false`)

## Cookies

| Cookie | httpOnly | Path |
|--------|----------|------|
| `chokmoki_admin_access` | yes | `/` |
| `chokmoki_admin_refresh` | yes | `/api/admin` |
| `chokmoki_csrf` | no | `/` |

## Environment

```env
JWT_ACCESS_TTL_MINUTES=60
JWT_REFRESH_TTL_DAYS=7
JWT_SECRET_PREVIOUS=           # optional rotation window
ADMIN_MFA_SECRET=              # optional base32 TOTP secret
CSRF_ENABLED=true
ADMIN_COOKIE_SAMESITE=lax      # use `none` + HTTPS for cross-origin API
ADMIN_COOKIE_DOMAIN=.example.com
ADMIN_LEGACY_BEARER_ENABLED=true
```

## Frontend

- Vite dev proxy: `/api` → `http://localhost:8000` (same-origin cookies)
- No JWT in localStorage; session via cookies + `/api/admin/me`
- Logout calls `POST /api/admin/logout`

## Production cross-origin

If storefront and API are on different domains:

1. Set `CORS_ALLOWED_ORIGINS` to the storefront origin
2. Set `ADMIN_COOKIE_SAMESITE=none` and `ADMIN_COOKIE_SECURE=true`
3. Optionally set `ADMIN_COOKIE_DOMAIN` for subdomain sharing

## Tests

```bash
pytest __tests__/test_security_phase2.py -v
```
