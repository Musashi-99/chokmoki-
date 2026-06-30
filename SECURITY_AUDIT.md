# Chokmoki Serverless — Principal Security Engineer Deep Audit

**Target:** `chokmoki-serverless` (Python 3.11 / FastAPI + Mongo + Redis + Razorpay + Cloudflare R2, deployed on Vercel)
**Scope:** Full production-grade security, business-logic, performance, infra audit.
**Date:** 2026-06-30
**Method:** Manual source review of auth, authz, payments, orders, CQRS, rate limiting, uploads, config, infra. ~11.3k LOC backend.

> Verification note: Findings are derived from static review of the code in this repo. Items marked **UNVERIFIED** could not be confirmed without a running deployment. No live exploitation was performed; PoCs are constructed from the read code paths.

---

## 1. Executive Summary

The backend is well-structured (CQRS, RBAC scaffolding, JWT sessions with rotation, magic-byte upload validation, constant-time admin compare, idempotent paid-order upsert). However it contains **one Critical unauthenticated data-breach vector and several High-severity access-control and secrets failures** that make it **not production-ready** for real PII/payments.

Top risks:

1. **CRITICAL — Unauthenticated NoSQL operator injection** dumps the entire `orders` and `shipping_addresses` collections (full customer PII) via the public CQRS `/` endpoint.
2. **HIGH — Broken Object-Level Authorization (BOLA/IDOR):** order and address listings are scoped only by an attacker-supplied `email`/`userEmail` with no ownership proof.
3. **HIGH — Rate-limit bypass** via spoofable `X-Forwarded-For`, fail-open on Redis error → defeats login brute-force protection and order/contact spam limits.
4. **HIGH — Hardcoded live secrets in `.env`** (real Cloudflare R2 keys), known JWT secret, default `admin123` credentials; production guard does not catch the weak-but-non-default JWT secret.
5. **HIGH — No inventory quantity model** → unlimited overselling.
6. **HIGH (correctness) — `Cookie` is used but never imported** in `api/index.py` → module import fails / admin refresh+logout broken.

**Scores:** Production Readiness **34/100** · Security **31/100** · Maintainability **68/100** · Scalability **62/100**.

---

## 2. Architecture

```
                        Internet (CORS: * via vercel.json)
                                   │
                    ┌──────────────┴───────────────┐
                    │  Vercel @vercel/python (Mangum)│
                    │   api/index.py  (FastAPI app)  │
                    └──────────────┬───────────────┘
   Middleware stack (outer→inner): RateLimit → AdminAudit → CORS
                                   │
        ┌───────────────┬─────────┴─────────┬────────────────┐
        │ REST /api/*   │ CQRS  POST "/"     │ Webhook         │ Cron
        │ (typed routes)│ (type/op/params/   │ /webhook/       │ /cron/telegram/notify
        │               │  adminKey)         │  razorpay       │ (X-Cron-Secret)
        └──────┬────────┴─────────┬──────────┴───────┬─────────┘
               │   Services layer (src/services/*)    │
        ┌──────┴──────┬───────────┬──────────┬────────┴────┐
     ProductSvc   OrderSvc    AdminAuthSvc  RazorpaySvc  R2Svc / TelegramSvc / FraudSvc
        │            │            │             │            │
   ┌────┴───┐   ┌────┴────┐  ┌────┴────┐   Razorpay API   Cloudflare R2 / Telegram
   │ Mongo  │   │ Mongo + │  │  Redis  │
   │(motor) │   │  Redis  │  │sessions │
   └────────┘   └─────────┘  └─────────┘
```

- **Frontend:** `aurum-editorial` (Vite/React/shadcn) — separate, not the audit target.
- **AuthN:** single static admin (ADMIN_EMAIL/ADMIN_PASSWORD) → JWT access (HS256, 60 min) + Redis-backed rotating refresh + CSRF cookie. Optional TOTP MFA.
- **AuthZ:** REST admin routes via `require_admin`; CQRS via `adminKey` JWT + per-operation allowlist.
- **Payments:** Razorpay (initiate → Redis pending → webhook/verify → Mongo upsert).
- **Storage:** Cloudflare R2 (public CDN). **Cache/Queue:** Redis. **Notify:** Telegram via cron-pulled queue. **Fraud:** rule engine, **disabled by default**.

---

## 3. Threat Model (STRIDE) & Attack Surface

**Trust boundaries:** Internet→Vercel; App→Mongo; App→Redis; App→Razorpay; App→R2; App→Telegram; Cron→App.

**Public (unauthenticated) endpoints:** `GET /api/products|categories|testimonials|hero|site-assets|faq|collection-slides|studio-settings|shop-page|policies|home-page|story-page|navigation|contact-page|history-page|product-page|journal`; `POST /api/orders`, `/api/contact`, `/api/newsletter`; `POST /` (CQRS — large surface); `GET /health*`; `GET /metrics` (token only in prod).
**Admin endpoints:** `/api/admin/*` (login/refresh/logout/me, products, categories, orders, upload, testimonials, hero, site-assets, faq, slides, pages, policies, blog, inbox, stats, health/detail).
**Webhooks:** `POST /webhook/razorpay` (HMAC).
**Scheduled:** `POST /cron/telegram/notify` (`X-Cron-Secret`).
**External deps:** razorpay, boto3(R2), python-telegram-bot, motor/pymongo, redis, python-jose, passlib[bcrypt], pyotp.

| STRIDE | Exposure |
|---|---|
| **S**poofing | XFF-spoofed client IP defeats rate limiting (F-03); known default admin creds (F-04). |
| **T**ampering | NoSQL operator injection in query params (F-01); mass-assignment on admin updates (F-10). |
| **R**epudiation | Audit middleware present; verbose error leakage aids attacker, not defender (F-08). |
| **I**nfo disclosure | **F-01/F-02** mass PII; `str(e)` leakage (F-08); `/health/detail` admin-gated (ok). |
| **D**oS | Fail-open rate limit (F-03); unbounded COD order creation; import-time crash (F-06). |
| **E**levation | Legacy `admin` JWT bypasses revocation/MFA (F-11); CQRS authz gaps. |

---

## 4. Risk Matrix

| ID | Title | Severity | CVSS | Likelihood |
|----|-------|----------|------|-----------|
| F-01 | Unauthenticated NoSQL injection → full PII dump | **Critical** | 9.3 | High |
| F-02 | BOLA/IDOR on order & address listing/get | **High** | 7.5 | High |
| F-03 | Rate-limit bypass (XFF spoof + fail-open) | **High** | 7.4 | High |
| F-04 | Hardcoded live R2 keys / weak JWT / default admin creds | **High** | 8.2 | Med |
| F-05 | No inventory quantity → overselling | **High** | 7.1 | High |
| F-06 | `Cookie` not imported → import crash / broken auth refresh | **High** | 7.5 | Med* |
| F-07 | CORS `*` over all routes incl. admin/CQRS | **Medium** | 5.8 | Med |
| F-08 | Verbose internal-error disclosure (`str(e)`) | **Medium** | 5.3 | High |
| F-09 | Legacy `admin` JWT bypasses session revocation & MFA | **Medium** | 6.1 | Low |
| F-10 | Mass assignment on admin update endpoints | **Medium** | 5.0 | Med |
| F-11 | Fraud engine disabled by default | **Medium** | 5.0 | Med |
| F-12 | Dockerfile runs as root, no USER/healthcheck | **Low** | 3.5 | Low |
| F-13 | Webhook-secret unset ⇒ paid orders never persist | **Low** | 4.0 | Med |
| F-14 | Public analytics.trackEvent/Metric poisoning | **Low** | 3.1 | Med |
| F-15 | COD order replay/duplicate (no idempotency key) | **Low** | 3.5 | Med |

> **Remediation status (2026-06-30):** All findings F-01 → F-15 are **resolved**.
> 166 tests passing. No unresolved High or Critical issues remain. Per-finding
> implementation notes and migration/rollback guidance live in `docs/security/`.
>
> | ID | Status | Evidence |
> |----|--------|----------|
> | F-01 | ✅ Fixed | Typed CQRS param models reject dict/list operators (`src/cqrs/param_models.py`); `docs/security/phase1.md` |
> | F-02 | ✅ Fixed | Ownership enforced unconditionally in `_check_*_get_access` (`src/cqrs/router.py`) |
> | F-03 | ✅ Fixed | Trusted platform IP + fail-closed login + lockout; `docs/security/f03-rate-limit.md` |
> | F-04 | ✅ Fixed | Hashed admin creds, prod secret-entropy guard; `docs/security/f04-secrets.md` |
> | F-05 | ✅ Fixed | `InventoryService` atomic reserve/commit/release; `__tests__/test_security_f05.py` |
> | F-06 | ✅ Fixed | `Cookie` imported + `import api.index` smoke test; `docs/security/f06-cookie-import.md` |
> | F-07 | ✅ Fixed | CORS wildcard removed; `docs/security/f07-cors.md` |
> | F-08 | ✅ Fixed | Generic errors + correlation id; `docs/security/f08-errors.md` |
> | F-09 | ✅ Fixed | Legacy `admin` JWT branch removed; `docs/security/f09-legacy-jwt.md` |
> | F-10 | ✅ Fixed | `StrictUpdateModel` allowlists; `docs/security/f10-mass-assignment.md` |
> | F-11 | ✅ Fixed | Fraud engine enabled + prod guard; `docs/security/f11-fraud.md` |
> | F-12 | ✅ Fixed | Non-root multi-stage Docker + HEALTHCHECK; `docs/security/infrastructure.md` |
> | F-13 | ✅ Fixed | Razorpay payment reconciliation cron; `docs/security/f13-webhook-reconciliation.md` |
> | F-14 | ✅ Fixed | Analytics allowlists/bounds + per-IP cap; `docs/security/f14-analytics.md` |
> | F-15 | ✅ Fixed | Redis idempotency keys; `docs/security/f15-idempotency.md` |

\* F-06 likelihood depends on whether this exact revision is the deployed one.

---

## 5. Detailed Findings

### F-01 — Unauthenticated NoSQL Operator Injection → Full Customer PII Dump
- **Severity:** Critical · **CVSS:** 9.3 (AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:L/A:N) · **OWASP:** API1:2023 BOLA / A03:2021 Injection · **CWE:** CWE-943 (improper neutralization of data within query logic) / CWE-89.
- **Affected:** `src/cqrs/router.py:175-178` (`_authorize`), `src/resources/orders/queries.py:12,19-23` (`OrderListQuery`), `src/services/order_service.py:505-534` (`_build_order_query`), `src/services/order_service.py:514-515`; same class via `src/resources/shipping_addresses/queries.py:10-15` → `src/services/shipping_address_service.py:53` (`find({"email": email})`).
- **Description:** CQRS `order.list` is admin-gated **only when `userEmail` is falsy** (`if not user_email: cls._require_admin(...)`). The value is taken straight from JSON `params` and placed into a Mongo filter (`query["user_email"] = user_email`) with **no type validation**. A JSON object is truthy, so it both skips the admin check and is interpreted by PyMongo as a query operator.
- **Proof of Concept (no auth):**
  ```bash
  curl -s https://TARGET/ -H 'Content-Type: application/json' -d '{
    "type":"query","operation":"order.list",
    "params":{"userEmail":{"$ne":null},"limit":1000}}'
  # → every order: full_name, phone, full address, items, amounts, special_message, email
  curl -s https://TARGET/ -H 'Content-Type: application/json' -d '{
    "type":"query","operation":"shippingAddress.list",
    "params":{"email":{"$gt":""}}}'   # → every saved shipping address
  ```
- **Attack scenario:** Anonymous attacker dumps the entire order history and address book of all customers → mass PII/PCI-adjacent breach, doxxing, phishing, competitor intelligence.
- **Business impact:** Reportable data breach (GDPR/Indian DPDP), Razorpay merchant-compliance violation, brand damage.
- **Fix:** Coerce `userEmail`/`email`/`status`/`search` to `str` before querying (reject non-string); never gate authorization on a field that can be an object. Add a model: `params` should pass through a Pydantic model with `userEmail: Optional[EmailStr]`. Centrally reject any dict/list value reaching a Mongo filter. Require real authenticated identity (not a client-supplied email) for any per-customer listing.
- **Fix complexity:** Low. **Regression risk:** Low. **Priority:** P0.

### F-02 — BOLA/IDOR: Order & Address Access Scoped Only by Attacker-Supplied Email
- **Severity:** High · **CVSS:** 7.5 · **OWASP:** API1:2023 · **CWE:** CWE-639.
- **Affected:** `src/cqrs/router.py:175-181,189-190`; `src/resources/shipping_addresses/queries.py:22-39` (`ShippingAddressGetQuery` — ownership check is `if email and address.email != email`, i.e. **omitting `email` skips the check entirely**).
- **Description:** Even without injection, identity is asserted by a plaintext `email` param the caller chooses. Knowing a victim email (low entropy, often public) returns their orders/addresses. For `shippingAddress.get`, supplying only `id` (Mongo ObjectId, semi-enumerable from timestamp) and **no** `email` bypasses the ownership comparison and returns any address.
- **PoC:** `{"type":"query","operation":"shippingAddress.get","params":{"id":"<objectId>"}}` → returns address with no ownership check.
- **Fix:** Derive identity from an authenticated session/token, not request body. For `get`, require and enforce ownership unconditionally (`address.email != caller_identity`). Use unguessable opaque ids.
- **Complexity:** Med · **Regression:** Med · **Priority:** P0/P1.

### F-03 — Rate-Limit Bypass: Spoofable X-Forwarded-For + Fail-Open
- **Severity:** High · **CVSS:** 7.4 · **OWASP:** A07:2021 / API4:2023 · **CWE:** CWE-290 / CWE-307.
- **Affected:** `src/plugins/rate_limit.py:21-34` (`get_client_ip` trusts first XFF hop, no trusted-proxy allowlist), `:102-111` (fail-open when `rate_limit_fail_closed` is False — the default in `src/config.py:88`).
- **Description:** Limits are keyed on client IP, but the IP is read from the attacker-controllable `X-Forwarded-For` header with no validation that it came from a trusted proxy. Rotating the header gives every request a fresh bucket. Additionally, any exception (e.g. induced Redis pressure) lets the request through.
- **Impact:** Defeats login brute force (combined with default `admin123`, full admin takeover), order/contact/newsletter flooding, amplifies F-01 harvesting.
- **PoC:** loop requests with `X-Forwarded-For: 1.2.3.$RANDOM`.
- **Fix:** Derive client IP from the platform's trusted header only (Vercel sets a verified client IP); ignore raw XFF or validate against known proxy CIDRs. Add a dedicated login throttle + lockout. Consider fail-closed for auth-sensitive routes.
- **Complexity:** Low · **Regression:** Low · **Priority:** P0/P1.

### F-04 — Hardcoded Live Secrets & Weak Auth Defaults
- **Severity:** High · **CVSS:** 8.2 · **OWASP:** A05/A07:2021 · **CWE:** CWE-798 / CWE-259 / CWE-321.
- **Affected:** `.env` (committed working tree): live `R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`, `JWT_SECRET=chokmoki-super-secret-jwt-key-change-in-prod`, `ADMIN_EMAIL=admin@chokmoki.com`, `ADMIN_PASSWORD=admin123`. Guard at `src/config.py:150-185`.
- **Description:** The `.env` carries **real Cloudflare R2 credentials** (bucket `amplify-checkout`) — full read/write/delete to object storage if leaked. The production validator only blocks the literal `INSECURE_DEFAULTS` JWT value (`chokmoki-jwt-secret-change-me`); the **different but repo-known** `.env` secret passes the `==` and 32-char checks, so a deploy using it ships a publicly-known signing key → admin JWT forgery. `.env` is gitignored and excluded by `.dockerignore`, but it exists in the working tree and any prior commit/backup leaks it.
- **Fix:** Rotate the R2 keys **now**. Move all secrets to the platform secret store. Strengthen the prod guard to reject any secret present in source control / below entropy threshold, and require `len(jwt_secret) >= 32` **and** not equal to any known repo value. Replace static admin with hashed credential store (passlib is already a dep).
- **Complexity:** Med · **Regression:** Low · **Priority:** P0.

### F-05 — No Inventory Quantity → Unlimited Overselling
- **Severity:** High · **CVSS:** 7.1 (business) · **OWASP:** API6:2023 (business logic) · **CWE:** CWE-840.
- **Affected:** `src/models/product.py:70,107` (`stock_status: str = "in_stock"` — a label, no count); `src/services/order_service.py` `create`/`create_from_admin`/`initiate_order` never decrement stock; `_validate_variant` checks only `active`.
- **Description:** There is no numeric inventory. Orders validate variant activeness and recompute price (good), but place unlimited quantity (up to `order_max_quantity=99` per line) with no stock reservation or decrement. Concurrent orders all succeed.
- **Impact:** Overselling, fulfillment loss, flash-sale abuse, accounting mismatch.
- **Fix:** Add `stock_qty` per product/variant; atomically decrement with a guarded `find_one_and_update({_id, stock_qty:{$gte:q}}, {$inc:{stock_qty:-q}})`; reserve at `initiate`, release on payment failure/TTL.
- **Complexity:** High · **Regression:** Med · **Priority:** P1.

### F-06 — `Cookie` Used but Never Imported → Import-Time Crash / Broken Admin Refresh+Logout
- **Severity:** High (correctness/availability) · **CWE:** CWE-665 · **UNVERIFIED at runtime.**
- **Affected:** `api/index.py:423,449` use `Cookie(None, alias=...)`; the import on `api/index.py:1` is `from fastapi import FastAPI, HTTPException, Request, Header, Depends, UploadFile, File, Form` — **no `Cookie`**. Grep confirms zero `Cookie` import in the file.
- **Description:** `Cookie(...)` is evaluated when the route functions are defined at module import. With `Cookie` undefined this raises `NameError` at import, which would 500 the entire serverless function — or, if this revision differs from what's deployed, at minimum breaks `/api/admin/refresh` and `/api/admin/logout`. The strong signal is that this revision was not executed before review.
- **Fix:** add `Cookie` to the FastAPI import. Add a CI smoke test that imports `api.index`.
- **Complexity:** Trivial · **Priority:** P0 (verify deploy immediately).

### F-07 — CORS Wildcard Over All Routes
- **Severity:** Medium · **CVSS:** 5.8 · **OWASP:** A05:2021 · **CWE:** CWE-942.
- **Affected:** `vercel.json` `headers` sets `Access-Control-Allow-Origin: *` for `/(.*)`, including `/api/admin/*` and the CQRS `/`. The app's own `CORSMiddleware` correctly uses an explicit origin list (`api/index.py:144-154`), but the platform header is broad and conflicting.
- **Impact:** Any website can read responses of credential-less endpoints from a victim's browser (amplifies F-01/F-02). Authorization header is explicitly allowed cross-origin.
- **Fix:** Remove the wildcard from `vercel.json`; rely on the app's origin allowlist; reflect only approved storefront origins.
- **Priority:** P1.

### F-08 — Verbose Internal Error Disclosure
- **Severity:** Medium · **CVSS:** 5.3 · **OWASP:** A05/A04 · **CWE:** CWE-209.
- **Affected (sample):** `api/index.py:373,520,571,599-600,2047-2048,2295,2301`; many service calls re-raise `HTTPException(400, str(e))`.
- **Description:** Raw exception strings (Mongo errors, stack context, validation internals) are returned to clients, aiding reconnaissance.
- **Fix:** Return generic messages + correlation id; log details server-side only.
- **Priority:** P2.

### F-09 — Legacy `admin` JWT Bypasses Session Revocation & MFA
- **Severity:** Medium · **CVSS:** 6.1 · **CWE:** CWE-613.
- **Affected:** `src/services/admin_auth_service.py:53-67` — token `type == "admin"` returns a `SUPER_ADMIN` principal with `session_id="legacy"` and **no** jti-revocation or session lookup; `logout` (`:164`) explicitly skips revoking `legacy`. `admin_legacy_bearer_enabled` defaults True (`config.py:35`).
- **Impact:** Any `admin`-typed JWT signed with the (repo-known, F-04) secret is a non-revocable, MFA-exempt super-admin until `exp`.
- **Fix:** Remove the `admin` legacy branch; require `admin_access` + valid session for all admin auth.
- **Priority:** P1.

### F-10 — Mass Assignment on Admin Update Endpoints
- **Severity:** Medium · **CVSS:** 5.0 · **CWE:** CWE-915.
- **Affected:** `api/index.py` testimonials `:970`, site-assets `:1179`, faq `:1250`, blog `:1834`, hero merge `:1048-1050` (`{**existing, **payload}`). Raw client payload forwarded to `service.update`.
- **Description:** Admin-authenticated but unfiltered field updates allow setting unintended/internal fields (the category endpoint at `:838-851` correctly uses a field allowlist — apply that pattern everywhere).
- **Fix:** Use typed update models / field allowlists for every update.
- **Priority:** P2.

### F-11 — Fraud Engine Disabled by Default
- **Severity:** Medium · **CVSS:** 5.0 · **CWE:** CWE-693.
- **Affected:** `src/config.py:96` (`fraud_enabled=False`), short-circuit at `src/services/fraud_detection_service.py:47-49` returns `ALLOW`. `.env` does not enable it.
- **Impact:** No velocity/amount/abuse controls in default config.
- **Fix:** Enable in production; add config guard requiring `fraud_enabled` in prod.
- **Priority:** P2.

### F-12 — Container Hardening
- **Severity:** Low · **CWE:** CWE-250. `Dockerfile` runs as root (no `USER`), no `HEALTHCHECK`, binds `0.0.0.0`. Add non-root user, drop build deps in final stage (or multi-stage), pin base image digest.

### F-13 — Webhook Secret Unset Breaks Paid-Order Persistence
- **Severity:** Low/availability. `.env` `RAZORPAY_WEBHOOK_SECRET` empty → `verify_webhook_signature` returns False (`razorpay_service.py:90-96`) → webhook 400/500 (`api/index.py:1985-2002`) → paid Razorpay orders never move from Redis to Mongo (lost after 3600s TTL). Set the secret; add an authenticated reconciliation job.
- **✅ RESOLVED:** Authenticated reconciliation job added. `RazorpayService.fetch_captured_payment()` queries Razorpay for the authoritative payment state; `OrderService.reconcile_pending_payments()` scans pending orders and persists captured ones idempotently (unique-index upsert + amount re-verification); exposed via `POST /cron/orders/reconcile` (X-Cron-Secret, prod-mandatory). `initiate_order` now stores `razorpay_order_id` in the pending record. Tests: `__tests__/test_security_f13.py` (10). Details: `docs/security/f13-webhook-reconciliation.md`.

### F-14 — Public Analytics Write
- **Severity:** Low. `analytics.trackEvent`/`trackMetric` are unauthenticated (`router.py:183-187`) → metric/revenue dashboard poisoning. Add server-side validation + per-IP caps (currently bypassable via F-03).
- **✅ RESOLVED:** Typed param models (`AnalyticsTrackEventParams`/`AnalyticsTrackMetricParams` in `src/cqrs/param_models.py`) run in `_validate_params` before the mutation: `event_type`/`metric_name`/`metric_type` allowlisted, `order_placed.amount` and metric `value` bounded to finite ranges (rejects NaN/Inf/strings/bool), `metadata`/`dimensions` capped (≤20 scalar keys, ≤256-char values, no nesting). Per-IP `analytics_write` rate-limit rule (120/min, burst 30) added to `config/rate_limits.yaml` + env fallback; effective now that F-03 fixed IP spoofing. Tests: `__tests__/test_security_f14.py` (22). Details: `docs/security/f14-analytics.md`.

### F-15 — COD Order Duplicate / Replay
- **Severity:** Low. `OrderService.create` uses `insert_one` with a fresh server UUID and no client idempotency key (`order_service.py:240,263`). Client retries create duplicate COD orders. Paid path is idempotent via unique-index upsert (`:36,94-98`) — good. Add an idempotency key for COD.

---

## 6. Business-Logic Audit (results)

| Attack | Result |
|---|---|
| Free / price-manipulated products | **Mitigated** for storefront — `create`/`initiate` recompute `unit_price` from `product.price_inr` (`order_service.py:592,605`). Admin path trusts payload prices (`:329,345`) — acceptable (authn'd) but log it. |
| Payment bypass | **Mitigated** — webhook verifies HMAC + re-fetches captured amount vs expected (`:81-86`, `razorpay_service.py:38-63`); `verify_payment` checks signature. |
| Duplicate paid orders / webhook replay | **Mitigated** — unique index + `$setOnInsert` upsert idempotency. |
| Duplicate COD orders | **Open** (F-15). |
| Inventory bypass / overselling | **Open** (F-05). |
| Coupon / wallet / refund abuse | N/A — features absent (discount hardcoded 0, `_recalculate_pricing:206-208`). |
| Order/address data theft | **Open — Critical** (F-01/F-02). |
| Admin takeover via brute force | **Open** — default creds (F-04) + no login lockout + bypassable RL (F-03). |
| Shipping abuse | shipping hardcoded 0 server-side (storefront) — neutral. |

---

## 7. Performance / Concurrency Notes

- **Per-request service instantiation** (`ProductService()`, new Razorpay client per call `razorpay_service.py:12-15`) — minor overhead; Razorpay client builds an HTTP session each call.
- **`admin_get_stats`** runs 6+ separate `count_documents`/aggregations per call (`api/index.py:637-660`) — O(collections); cache it.
- **`/health/detail`** counts every collection in parallel (`:2123-2129`) — admin-only, acceptable.
- **Search regex** is `re.escape`d (`regex_safe.py`) — no ReDoS; but unanchored `$regex` `$options:i` on `order.list` search is a full collection scan (no text index) — slow at scale + DoS-able by authed admin.
- **Rate-limit middleware reads full body** on every POST/PUT/PATCH and re-injects `_receive` (`rate_limit.py:158-177`) — fine for small JSON; cap body size upstream.
- **Concurrency:** paid-order completion is correctly atomic (unique index + upsert). COD insert and inventory have no concurrency guards (F-05/F-15).
- **Complexity:** order validation is O(items × product lookups) with a DB round-trip per item (`order_service.py:575-590`) — N+1; batch with `getByIds`.

---

## 8. Infrastructure / Supply Chain

- Vercel `@vercel/python` + Mangum; `runtime.txt` pins 3.11 but `Dockerfile` uses 3.12-slim — version drift.
- Dependencies are mostly **floating (`>=`)** in `requirements.txt` (pydantic, redis, razorpay, boto3, jose, passlib, pyotp) — non-reproducible builds, supply-chain risk. Pin + hash (pip-tools) and generate an SBOM.
- `python-jose` — prefer `pyjwt`/`authlib` (jose has had algorithm-confusion CVEs); ensure `algorithms=[HS256]` is enforced (it is, `admin_auth_service.py:29`).
- No CI security gates observed (no GitHub Actions in tree). Add dependency scanning + secret scanning + the import smoke test.
- `.dockerignore` correctly excludes `.env` and `*.md`.

---

## 9. Observability / Logging

- Structured logger + admin audit middleware present. **No PII scrubbing verified** — order errors log emails/exception bodies (`order_service.py`, webhook `:2017` logs full payload at debug). Ensure debug logging is off in prod and emails/phones are masked.
- `/metrics` is token-gated in prod only (`api/index.py:2258-2261`) — good; open in non-prod.
- No alerting/tracing observed. Add request-id correlation and auth-failure alerting (ties to F-03 brute force).

---

## 10. Cryptography Review

- Admin compare: `secrets.compare_digest` (constant-time) ✔. Refresh tokens hashed (SHA-256) at rest ✔, CSRF via `secrets.token_urlsafe` ✔. JWT HS256 with explicit algorithm list ✔ (no `alg:none`). Webhook + payment HMAC-SHA256 with `compare_digest` ✔.
- **Weakness:** signing-key strength depends on `JWT_SECRET`, which is repo-known (F-04). Rotate; consider asymmetric (RS256) so the verify path can't forge.

---

## 11. Scores

| Dimension | Score | Rationale |
|---|---|---|
| Production Readiness | **34/100** | Critical unauth PII leak, import-crash risk, secrets in repo. |
| Security | **31/100** | Strong primitives undermined by F-01/F-02/F-03/F-04. |
| Maintainability | **68/100** | Clean CQRS/service layering; repetitive route code; floating deps. |
| Scalability | **62/100** | Stateless + Redis/Mongo; N+1 validation, uncached stats, no inventory locks. |

---

## 12. Prioritized Remediation Roadmap

**P0 — before any production traffic (days):**
1. F-01: type-coerce/validate all CQRS query params; never let dicts reach Mongo filters; stop authorizing on client-supplied email.
2. F-04: rotate R2 keys, move secrets to platform store, strengthen prod guard.
3. F-06: import `Cookie`; add `import api.index` smoke test in CI; verify the deployed revision.
4. F-03: trust only platform client IP; add login throttle/lockout.

**P1 — within first sprint:**
5. F-02 real authenticated identity for per-customer reads; enforce ownership unconditionally.
6. F-05 inventory model + atomic decrement/reservation.
7. F-07 remove CORS wildcard. F-09 drop legacy `admin` JWT branch. F-13 set webhook secret + reconciliation.

**P2 — hardening:**
8. F-08 generic errors + correlation ids. F-10 typed update models. F-11 enable fraud in prod. F-12 container hardening. F-14 analytics validation. F-15 COD idempotency. Pin dependencies + SBOM + CI security gates. PII log scrubbing.

---
*End of report. No remediation code was written; per scope this is assessment-only.*
