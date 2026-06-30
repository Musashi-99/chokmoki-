## Fraud Detection Subsystem

### Architecture
- **Entry points**: `OrderService.create`, `OrderService.initiate_order`, `OrderService.create_from_admin`
- **Core engine**: `src/fraud/engine.py` evaluates rules over a normalized context
- **Rules**: `config/fraud_rules.yaml` (YAML) or JSON equivalent
- **Hot reload**: rules are reloaded when the file mtime changes (per-process cache)
- **Audit trail**: MongoDB collection `fraud_decisions` (best-effort; never blocks)
- **Logs**: JSONL events via `src/plugins/structured_log.py` (`module="fraud"`)
- **Metrics**: Prometheus counters/histograms in `src/plugins/metrics.py` and `/metrics`

### Rule Format (YAML)
- **RuleSet**: `id`, `version`, optional `groups`, and `rules`
- **Groups**: provide `defaults` merged into member rules (inheritance)
- **Rules**:
  - `priority`: higher runs first
  - `severity`: influences risk aggregation weight
  - `risk`: 0–100
  - `confidence`: 0–100
  - `action`: `allow|challenge|manual_review|reject`
  - `when`: list of conditions (AND semantics)

Supported condition ops:
- `exists`
- `equals`
- `in`
- `contains`
- `regex` (case-insensitive)
- `cidr`
- `gt|gte|lt|lte`

### Configuration
Environment variables:
- `FRAUD_ENABLED` (default: false)
- `FRAUD_FAIL_CLOSED` (default: false)
- `FRAUD_RULES_FILE` (default: `config/fraud_rules.yaml`)
- `FRAUD_AUDIT_ENABLED` (default: true)

Metrics:
- `METRICS_ENABLED` (default: true)
- `METRICS_TOKEN` (production auth for `/metrics`)

### Rollback Strategy
- **Immediate rollback**: set `FRAUD_ENABLED=0` (engine bypasses with `allow`)
- **Fail-open safety**: leave `FRAUD_FAIL_CLOSED=0` to prevent accidental rejects if rules load fails
- **Fail-closed mode**: set `FRAUD_FAIL_CLOSED=1` only when rules management and monitoring are mature

### Operational Notes
- Rule changes are picked up automatically by mtime hot reload (no deploy required).
- Audit failures never block checkout; monitor logs/metrics to detect missing audits.

