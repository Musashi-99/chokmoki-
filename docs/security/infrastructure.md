# Infrastructure Hardening

## Changes
- Multi-stage `Dockerfile` with non-root `app` user (uid 10001)
- `HEALTHCHECK` against `GET /health`
- Pinned runtime dependencies in `requirements.txt`
- `requirements-dev.txt` for security tooling
- `.github/workflows/security-ci.yml` — pytest, Bandit, pip-audit, Semgrep, SBOM, Gitleaks, Trivy

## CI gates
Pull requests must pass tests and security scans before merge. Container images are scanned for CRITICAL/HIGH CVEs.

## SBOM
CI generates `sbom.cdx.json` via CycloneDX. Run locally:
```bash
pip install cyclonedx-bom
cyclonedx-py requirements -i requirements.txt -o sbom.cdx.json
```
