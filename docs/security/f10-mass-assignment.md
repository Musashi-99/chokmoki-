# F-10 — Mass Assignment Hardening

## Vulnerability
Admin-authenticated update endpoints accepted raw JSON and forwarded it to MongoDB services, allowing clients to set internal/protected fields (`_id`, `created_at`, etc.).

## Root cause
Missing typed update models and field allowlists on testimonials, hero, site assets, FAQ, blog, products, collection slides, and policy sections.

## Changes
- `src/security/mass_assignment.py` — `StrictUpdateModel`, `build_update_payload`, protected field stripping
- Typed `*Update` models on all affected resources
- Admin routes validate updates before calling services

## Migration
Deploy as-is. Admin clients sending unknown fields receive `400 Invalid request parameters`.

## Rollback
Revert `api/index.py` update handlers and remove `*Update` model usage.

## Security impact
Eliminates CWE-915 mass assignment on admin mutation paths.
