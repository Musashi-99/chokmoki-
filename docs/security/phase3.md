# Phase 3 — Token Bucket Rate Limiter

## Architecture

- Redis Lua script (`src/plugins/rate_limit_lua.lua`) — atomic token bucket with burst
- Rule engine (`src/plugins/rate_limit_config.py`) — YAML + env fallback
- Default rules (`config/rate_limits.yaml`)
- Middleware (`src/plugins/rate_limit.py`) — resolves IP, email, admin, endpoint buckets

## Buckets

| Scope | Key pattern |
|-------|-------------|
| IP | `rl:ip:{rule_id}:{ip}` |
| Email | `rl:email:{rule_id}:{sha256}` |
| Admin | `rl:admin:{rule_id}:{email}` |
| Endpoint | `rl:endpoint:{rule_id}:{path}` |

## Configuration

```env
RATE_LIMIT_ENABLED=true
RATE_LIMIT_FAIL_CLOSED=false
RATE_LIMIT_CONFIG_FILE=config/rate_limits.yaml
```

Override rules by editing YAML or setting `RATE_LIMIT_CONFIG_FILE`.

## Response

HTTP `429` with `Retry-After` header (seconds).

## Tests

```bash
pytest __tests__/test_rate_limit_phase3.py -v
```
