# F-04 — Secrets Hardening

## Changes

- Known-weak secret blocklist including repo-documented defaults
- Shannon entropy validation for JWT, cron, metrics, and R2 secrets
- Production requires `ADMIN_PASSWORD_HASH` (bcrypt); plaintext `ADMIN_PASSWORD` rejected when hash is set
- `JWT_SECRET_PREVIOUS` validated during rotation window
- R2 credential pairing validation
- Removed live credentials from local `.env` templates

## Generate admin password hash

```bash
python scripts/generate_admin_password_hash.py
```

Set output as `ADMIN_PASSWORD_HASH` in Vercel/platform secrets.

## Generate JWT secret

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Production environment

```env
ENVIRONMENT=production
JWT_SECRET=<48+ char random>
JWT_SECRET_PREVIOUS=<optional previous key during rotation>
ADMIN_PASSWORD_HASH=<bcrypt hash>
CRON_SECRET=<min 16 chars, high entropy>
METRICS_TOKEN=<min 16 chars, high entropy>
CORS_ALLOWED_ORIGINS=https://your-store.com
R2_ACCESS_KEY_ID=<from Cloudflare after rotation>
R2_SECRET_ACCESS_KEY=<from Cloudflare after rotation>
```

Do **not** set `ADMIN_PASSWORD` in production when using `ADMIN_PASSWORD_HASH`.

## JWT rotation

1. Set `JWT_SECRET_PREVIOUS` to the current `JWT_SECRET`
2. Deploy new random `JWT_SECRET`
3. Wait for existing access tokens to expire
4. Remove `JWT_SECRET_PREVIOUS`

## R2 key rotation

1. Create new R2 API token in Cloudflare
2. Update deployment secrets
3. Revoke the old token immediately

## Migration

1. Rotate compromised R2 keys in Cloudflare
2. Generate new `JWT_SECRET` and redeploy
3. Run `scripts/generate_admin_password_hash.py`
4. Set `ADMIN_PASSWORD_HASH` in Vercel; remove `ADMIN_PASSWORD`
5. Copy `.env.example` to `.env` for local dev

## Rollback

Revert the F-04 commit and restore prior env vars from backup. Rotate all secrets again after rollback testing.

## Tests

```bash
pytest __tests__/test_security_f04.py -v
```

## Performance impact

Negligible — validation runs once at startup; bcrypt verify adds ~100ms per login.

## Security impact

Blocks known weak/repo-leaked secrets; enforces hashed admin credentials in production; supports JWT rotation.
