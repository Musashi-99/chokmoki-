# F-09 — Legacy JWT Removal

## Changes

- Removed acceptance of `type: "admin"` JWTs
- All admin auth requires `type: "admin_access"` with valid `jti`, `sid`, and Redis session
- CQRS `adminKey` validated via full session lookup (not decode-only)
- Logout always revokes jti + session
- `ADMIN_LEGACY_BEARER_ENABLED` defaults to `false`; blocked in production

## Migration

1. Re-login via `/api/admin/login` to obtain session-backed cookies
2. For CQRS clients: pass the `admin_access` JWT from login (or cookie) as `adminKey`
3. Retire any tooling that minted `type: "admin"` tokens
4. Set `ADMIN_LEGACY_BEARER_ENABLED=false` in all environments

## Breaking changes

- Pre-session `type: "admin"` JWTs no longer work
- CQRS admin operations require a live session (revoked tokens fail immediately)

## Rollback

Revert the F-09 commit. Legacy tokens work again but re-open the revocation bypass.

## Tests

```bash
pytest __tests__/test_security_f09.py -v
```
