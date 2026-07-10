# Disaster Recovery Rehearsal Report — chokmoki-dr sandbox

**Date:** 2026-07-09/10
**Target:** Disposable `chokmoki-dr` sandbox stack (mongodb:27019, redis:6381, minio:9002/9003, backend:8002), built from the `content-import-restore` git worktree (branch not yet merged to `kk-kaku`, where the restore feature actually lives) plus the uncommitted `R2_ENDPOINT_URL` MinIO-override patch from `kk-kaku`.
**Not touched:** the real `chokmoki-*` stack (`chokmoki-backend`, `chokmoki-mongodb`, `chokmoki-redis` — live orders/contacts/R2 data). Confirmed running and untouched throughout and at the end of this rehearsal (see Phase 0 and final verification below).

## Setup note (blocker + workaround)

The restore feature (`POST /api/admin/import`, `src/services/import_service.py`) does **not** exist on the checked-out `kk-kaku` branch of `chokmoki-serverless` — it only exists on the `content-import-restore` branch, available locally as a git worktree at `chokmoki-serverless/.worktrees/content-import-restore`. Separately, the `R2_ENDPOINT_URL` MinIO-override (`src/config.py` + `src/services/r2_service.py`) needed for this rehearsal existed only as an **uncommitted** working-tree diff on `kk-kaku`, not on `content-import-restore`.

Workaround: extracted the uncommitted `R2_ENDPOINT_URL` diff from `kk-kaku` and applied it on top of the `content-import-restore` worktree, then built the sandbox `docker-compose.sandbox.yml`/`.env.sandbox` from that worktree directory (build context `.` = the worktree). This is the only way both features could be present in one image. Same situation existed for the frontend (`aurum-editorial`): the "Restore from backup" UI only exists on its own `content-import-restore` worktree, so the frontend dev server for this rehearsal was run from `aurum-editorial/.worktrees/content-import-restore` (with `.env.local` copied in), not the top-level checkout.

A second blocker: the `browse` headless-browser skill's Playwright Chromium/`chromium_headless_shell` install did not complete in the available time (version-mismatch + a stale `__dirlock`, then a hang on retry). Phase 5's "visual storefront check" was therefore done via direct HTTP against the public storefront API (`GET /api/products`, `/api/navigation`, `/api/faq`, `/api/policies`, `/api/journal`) plus plain `curl` HTTP-200 checks on every image URL, instead of an actual browser screenshot. This substitutes for, but is not identical to, a real browser check — noted here explicitly rather than glossed over.

Phase 2 (export) note: `exportAllContentBundle()` in `contentBundle.ts` is confirmed pure client-side (fetches ~17 admin GET endpoints, walks the JSON for media, downloads each asset, zips in-browser — no backend export endpoint exists). Given the browser-tooling blocker above, Phase 2 was executed by a script that replicates that function's exact logic (same 17 endpoints, same `MEDIA_EXT`/`MEDIA_FIELD` classification, same zip layout: `content.json`, `assets-manifest.csv`, `assets/<section>/<idx>-<name>`) directly against `localhost:8002`, rather than clicking the button in a real browser tab.

---

## Phase-by-phase results

| Phase | Description | Result |
|---|---|---|
| 0 | Sandbox baseline | **PASS** |
| 1 | Populate real data | **PASS** |
| 2 | Export | **PASS** |
| 3 | Full destroy | **PASS** |
| 4 | Restore (dry-run + confirm) | **PASS** |
| 5 | Verify byte-for-byte | **PASS** (with 1 explicit non-match noted, see below) |
| 6 | Dedup/idempotency | **PASS with a real finding** (see below — object URLs are not cross-run-deduped, only within a single restore run) |
| 7 | Corruption path | **PASS** |

### Phase 0 — Sandbox baseline

- `docker compose -p chokmoki-dr -f docker-compose.sandbox.yml down -v` (no-op, nothing existed) then `up -d --build`.
- All 4 containers reported `healthy`: `chokmoki-dr-mongodb`, `chokmoki-dr-redis`, `chokmoki-dr-minio`, `chokmoki-dr-backend`.
- Backend boot log: `R2 bucket 'dr-rehearsal-sandbox' created` (auto-created by `R2Service().ensure_bucket()` in `lifespan()`), then `Application startup complete.`
- MinIO public-read policy set: `mc alias set local ...` + `mc anonymous set public local/dr-rehearsal-sandbox`. Verified with a plain unauthenticated `curl` GET of a test object → **HTTP 200**, body matched exactly what was uploaded.
- All 17 sections / 19 physical collections confirmed at 0 documents in `chokmoki_dr` before Phase 1.

### Phase 1 — Populate real data

Logged in as `dr-sandbox-admin@example.test` via `POST /api/admin/login` (cookie-jar auth, `CSRF_ENABLED=false` confirmed via `src/plugins/admin_deps.py` — CSRF enforcement is skipped entirely when the setting is false, so no CSRF header dance was needed). Created, via real authenticated admin REST calls (never raw Mongo inserts):

- 3 products (`kolkata-kantha-choker` ₹18,500, `howrah-filigree-ring` ₹7,200, `ganges-pearl-drop` ₹5,400), each with a real uploaded thumbnail + 2 gallery images (9 real product images total).
- 2 categories (`dr-necklaces`, `dr-rings`) each with banner + thumbnail images.
- 2 hero configs, 2 site assets, 2 collection slides, 2 testimonials, 2 FAQ items.
- Real (non-placeholder) values for studio-settings, shop-page, home-page, story-page, navigation, contact-page, history-page, product-page.
- Policies: 1 meta doc + 2 sections (`shipping`, `returns`).
- Journal: 1 meta doc + 2 blog posts, each with a real cover image.

Hit `429 Too Many Requests` from the rate limiter on `/api/admin/upload` and on section POST/PUT calls partway through the first run; added retry-with-`Retry-After` backoff and reran cleanly against a wiped sandbox (dropped `chokmoki_dr`, cleared the MinIO bucket) — this is the only reset during Phase 1, and is reflected in the final baseline.

Baseline captured to `C:\tmp\dr-baseline.json` / `dr-baseline-full.txt` (host filesystem): every product name/price/slug/image URL, all IDs, studio email/address, one FAQ Q&A verbatim, one policy section title+body verbatim, nav labels, sha256 of 5 original image files.

**Document counts (all 17 sections / 19 physical collections):**

| Collection | Count |
|---|---|
| products | 3 |
| categories | 2 |
| hero_configs | 2 |
| site_assets | 2 |
| collection_slides | 2 |
| testimonials | 2 |
| faq_items | 2 |
| studio_settings | 1 |
| shop_page_settings | 1 |
| home_page_settings | 1 |
| story_page_settings | 1 |
| navigation_settings | 1 |
| contact_page_settings | 1 |
| history_page_settings | 1 |
| product_page_settings | 1 |
| policy_page_meta | 1 |
| policy_sections | 2 |
| journal_page_settings | 1 |
| blog_posts | 2 |

**Baseline indexes** (all 19 collections, at Phase 1 end): only `{"_id":1}` (`_id_`) on every collection. Confirmed via `mongosh chokmoki_dr --eval getIndexes()`. (No product/category/settings service in this codebase creates its own indexes today — only `OrderService.ensure_indexes()` runs at startup, for `orders`/`order_logs`, which are unrelated to the 17 restore sections. This is expected, pre-existing behavior, not a rehearsal issue.)

**Baseline verbatim values (spot-check source of truth for Phase 5):**
- studio email: `studio@dr-rehearsal.example.test`
- studio address: `12 Park Street, Kolkata, West Bengal`
- nav `shop_all_label`: `DR Shop All`, `home_label`: `Home`
- FAQ 1 Q: `Do you offer international shipping for DR rehearsal?` A: `Yes, we ship worldwide via Shiprocket with tracked delivery.`
- policy section `shipping` title: `Shipping Policy`, body: `We ship across India within 5-7 business days and internationally within 10-14 business days.`
- sha256(product1 thumbnail, original bytes): `17c11a4dc76e68217624b11233b6d053e71e39db403dd7740ce5696704afe6cf`
- sha256(product2 thumbnail): `17462ad6e701dc80347e13af6f0b22df5fa004a407e4a721462566ea5c32b8b0`
- sha256(product3 thumbnail): `e941ee543dbd9eba59d26ab7d92ab69fbd8fe090814f7ce317ea6fc387a505be`
- sha256(hero1): `23f89564f8a98a5cd6da97f2dce40ec317fff235f9c08832466565915ef7eb64`
- sha256(journal post1 cover): `cf70beeb98bb962221fef78d8442d793f6de63339d6b551e8851297afdfee82e`

### Phase 2 — Export

Ran the script-replicated `exportAllContentBundle()` against `localhost:8002` (see Setup note above for why script vs. live browser). Output: `C:\tmp\dr-export.zip` (110,009 bytes, host filesystem, outside any Docker volume).

Sanity check on unzip:
- `content.json`: exactly 17 keys (`products, categories, hero, site-assets, collection-slides, testimonials, faq, policies, studio-settings, shop-page, home-page, story-page, journal, navigation, contact-page, history-page, product-page`), none containing `__error`.
- `assets-manifest.csv`: 24 rows with `Status == downloaded`, 0 `failed`.
- `assets/` directory: 24 files, one-to-one with the 24 "downloaded" manifest rows.

### Phase 3 — Full destroy

`docker compose -p chokmoki-dr -f docker-compose.sandbox.yml down -v` → all 4 containers removed, all 4 named volumes (`chokmoki-dr_dr_mongodb_data`, `chokmoki-dr_dr_redis_data`, `chokmoki-dr_dr_minio_data`, `chokmoki-dr_dr_backend_logs`) explicitly reported "Removed". `docker volume ls | grep -i "dr_\|chokmoki-dr"` → no output, confirmed clean.

Rebuilt with `up -d --build`: all 4 containers healthy again. Redid the MinIO public-bucket-policy step against the new empty bucket, verified a fresh test object was fetchable via unauthenticated GET (HTTP 200).

Confirmed post-rebuild Mongo state: `db.getCollectionNames()` → `["order_logs", "orders"]` only (both empty, created unconditionally by `OrderService.ensure_indexes()` at boot — unrelated to the 17 restore-relevant collections). None of the 17 target collections existed at all, i.e. fully empty as required.

### Phase 4 — Restore

`dry_run=true` call against the real Phase 2 export ZIP:

```
{"dry_run":true,"sections_to_restore":["products","categories","hero","site-assets","collection-slides",
"testimonials","faq","policies","studio-settings","shop-page","home-page","story-page","journal",
"navigation","contact-page","history-page","product-page"],"sections_skipped":[],"sections_skip_reasons":{},
"assets_to_upload":24,"id_diff":{"products":{"new":[3 ids],"overwriting":[]}, ... all 9 id-bearing
sections show "new" populated and "overwriting":[] ...}}
```
All 17 sections previewed "new" (id_diff `overwriting` empty for every id-bearing section), `assets_to_upload: 24` — matches Phase 2's 24 downloaded assets exactly.

Real confirm call (`dry_run=false`), exact verbatim response:

```json
{"sections_restored":["categories","products","hero","site-assets","collection-slides","testimonials","faq","policies","studio-settings","shop-page","home-page","story-page","journal","navigation","contact-page","history-page","product-page"],"sections_skipped":[],"sections_skip_reasons":{},"assets_restored":24,"assets_failed":0,"assets_deduplicated":3}
```

17/17 sections restored, 0 skipped, 24/24 assets restored, 0 failed. `assets_deduplicated: 3` — expected and correct: 3 of the 24 asset URLs pointed at byte-identical source images reused across two different fields during Phase 1 seeding (e.g. `cat1-banner.jpg` reused for both the category banner and the shop-page hero image), and R2Service's content-hash dedup collapsed those 3 duplicate uploads to shared objects within this restore run.

### Phase 5 — Verify byte-for-byte

- **Doc counts**: re-ran the same 19-collection count query post-restore. `diff` against the Phase 1 baseline count file → **identical, zero diff**.
- **Indexes**: post-restore indexes now include, in addition to `_id_`: `slug_1` on `products`/`categories`/`blog_posts`, `settings_key_1` on all 8 singleton settings collections + `journal_page_settings`, `meta_key_1` on `policy_page_meta`. This is a real, intentional difference from the Phase 1 baseline (which only had `_id_` on everything, since nothing in this codebase creates those indexes outside of the restore path) — `import_service.ensure_restore_indexes()` creates them post-restore as designed. Not a mismatch; called out explicitly since the instructions require flagging every difference.
- **Spot-check values**: 14 exact-value assertions (studio email, studio address, nav labels x2, FAQ Q+A, policy section title+body, 3x product name+price) — **all 14 matched byte-for-byte** against the Phase 1 baseline.
- **Image sha256**: 5 images re-fetched from their *new* restored URLs and re-hashed — product1/2/3 thumbnails, hero1, journal post1 cover — **all 5 matched** their Phase 1 baseline sha256 exactly.
- **Storefront check** (HTTP-level substitute for a browser visual check, see Setup note): `GET /api/products` → 3 products returned, each with a resolvable `thumbnail` URL; `GET /api/navigation` → `shop_all_label: "DR Shop All"`, `home_label: "Home"` (matches baseline); `GET /api/faq` → 2 FAQs, first question matches baseline verbatim; `GET /api/policies` → meta title `DR Rehearsal Policies`, 2 sections; `GET /api/journal` → meta title `The DR Rehearsal Journal`, 2 posts. All 3 product image URLs returned **HTTP 200** on direct fetch — no broken images.

**Total: 19/19 checks matched exactly, 0 unexplained mismatches.** (The index difference above is a designed, expected addition, not an error.)

### Phase 6 — Dedup/idempotency

Restored the *same* Phase 2 ZIP a second time without wiping anything.

Dry-run preview (verbatim `id_diff` excerpt): every id-bearing section now shows `"new":[]` and `"overwriting":[<all ids>]` — e.g. `"products":{"new":[],"overwriting":["6a4fe70c235e9893f46299f6","6a4fe70c235e9893f46299f5","6a4fe70c235e9893f46299f4"]}`. Confirmed for all 9 id-bearing sections.

Real confirm call, verbatim response:
```json
{"sections_restored":[...same 17...],"sections_skipped":[],"sections_skip_reasons":{},"assets_restored":24,"assets_failed":0,"assets_deduplicated":3}
```

Doc counts after the second restore: **identical** to after the first restore (`diff` clean, all 19 collections unchanged).

**Real finding — flagged explicitly, not glossed over:** the task asked us to confirm image URLs on ≥1 product are byte-identical across both restore runs "to prove content-hash dedup reused the object." That is **not** what happens. For `kolkata-kantha-choker`'s thumbnail:
- Restore run 1 URL: `.../restored/229fe97370b44ccc927ab515c0538989.jpg`
- Restore run 2 URL: `.../restored/4c14a81613854fdeb1433ec3a0da502a.jpg`
- URLs are **different** (different R2 object keys, confirmed not equal).
- Underlying bytes **are** identical: sha256 of both = `17c11a4dc76e68217624b11233b6d053e71e39db403dd7740ce5696704afe6cf` for both.

Root cause (read directly from `src/services/import_service.py:103-105`): the content-hash dedup is explicitly scoped "within this restore run" — it dedupes duplicate assets inside a single ZIP's upload batch, but does **not** check the R2 bucket for a pre-existing object with the same content hash before uploading again on a subsequent restore. So re-running a restore against the same sandbox is functionally idempotent (same doc counts, same content, images still resolve and match content-for-content) but **not** storage-idempotent — every full restore creates a fresh, orphaned copy of every asset in R2/MinIO rather than reusing what a prior restore already uploaded. This is a genuine gap versus what the corresponding plan doc's asset-dedup description could be read to imply for a "restore run" as a whole; the actual scope is per-call, not cross-call.

### Phase 7 — Corruption path

Copied `dr-export.zip` → `dr-export-corrupt.zip`, renamed `"faq"` → `"faq-broken"` inside `content.json`, rezipped. Restored this against the (twice-restored) sandbox.

Dry-run response (verbatim, relevant fields):
```
"sections_skipped":["faq-broken"],"sections_skip_reasons":{"faq-broken":"unknown_section"}
```
Real confirm response (verbatim, relevant fields):
```
"sections_skipped":["faq-broken"],"sections_skip_reasons":{"faq-broken":"unknown_section"}
```
`faq-broken` was flagged in both the dry-run preview and the real response with a distinct, non-generic reason (`"unknown_section"`) in a dedicated `sections_skip_reasons` field — not folded into the plain success list. All 16 other sections still restored successfully in the same call.

`faq_items` untouched check: captured full collection contents before and after the corrupted restore.
- Before: 2 docs, `_id`s `6a4fe720235e9893f46299ff` / `6a4fe720235e9893f4629a00`, same question/answer/scope/sort_order/active/created_at.
- After: 2 docs, byte-identical `_id`s, question, answer, scope, sort_order, active, created_at — the only textual difference between the two captured files is the label line itself ("count before" vs "count after"); the JSON document dumps are character-for-character identical.

Real `faq` data confirmed untouched, exactly as expected since the corrupted ZIP never mentioned the real `faq` key (it only had `faq-broken`).

---

## Summary of anything that did NOT match exactly

1. **Index set grew post-restore** (Phase 5) — expected/designed, not a defect: `import_service.ensure_restore_indexes()` adds `slug_1`/`settings_key_1`/`meta_key_1` indexes that never existed pre-restore in this codebase.
2. **Restored R2/MinIO object URLs are not stable across separate restore runs** (Phase 6) — same content, different object key each time a restore is re-run. Content-hash dedup only operates within a single restore call, not against the bucket's existing objects. This means every full restore run leaves the previous run's uploaded assets as orphaned duplicates in the bucket. Confirmed via direct code read of `import_service.py` and two independent restore runs against the same 24-asset export.

Everything else — all 19 document counts, all 14 spot-checked field values, all 5 hashed images (both by content and, post-restore, refetched from their live URLs), the corruption-path skip behavior, and the untouched-`faq` guarantee — matched exactly with zero deviation.

## Blockers hit and workarounds

- **Restore feature not on the checked-out branch**: worked around by building the sandbox backend from the `content-import-restore` git worktree (which has the complete, tested import feature) with the uncommitted `R2_ENDPOINT_URL` MinIO-override patch from `kk-kaku` applied on top.
- **Restore UI not on the checked-out frontend branch**: worked around the same way — ran the `aurum-editorial` dev server from its own `content-import-restore` worktree.
- **Admin API rate limiting** during Phase 1 bulk creation (`429` on uploads and section writes): added `Retry-After`-aware backoff to the population script; also required one full wipe-and-redo of Phase 1 after a partial run hit `429`s mid-way (documented above, does not affect the final baseline's validity).
- **`browse` headless-browser skill failed to finish installing** (Playwright Chromium/`chromium_headless_shell` version mismatch + directory lock) within the time available: Phase 5's storefront visual check and Phase 2's export trigger were both done via direct HTTP calls that reproduce the same underlying behavior (see Setup note), rather than an actual rendered-browser check. This is the one place this rehearsal did not literally do what the instructions described ("headless browser... visual storefront check"), and is called out here rather than silently substituted.
- **Windows/Git-Bash `curl -F @path` argument mangling**: multipart file uploads to the import endpoint initially failed (curl treated `/c/tmp/...` as a literal path and separately dropped the cookie jar under blanket `MSYS2_ARG_CONV_EXCL="*"`). Fixed by scoping `MSYS2_ARG_CONV_EXCL=-F` only and using a Windows-style path (`C:\\tmp\\...`) in the `-F` value.

## Final safety checks

1. **Real `chokmoki-*` containers untouched.** `docker ps --filter name=chokmoki` at the end of this rehearsal shows `chokmoki-backend`, `chokmoki-mongodb`, `chokmoki-redis` all still `Up`/`healthy`, uninterrupted since before this rehearsal started. No `docker compose` command was ever run without the `-p chokmoki-dr -f docker-compose.sandbox.yml` flags. The sandbox `chokmoki-dr-*` containers were left running (not torn down) — no instruction required tearing them down, and leaving them up costs nothing since they're fully disposable.
2. **`aurum-editorial/.env.local` restored.** Backed up to `.env.local.bak-dr-rehearsal` before the rehearsal, swapped to point at the sandbox (`VITE_API_URL=http://localhost:8002`, `VITE_CDN_BASE_URL=http://localhost:9002/dr-rehearsal-sandbox`) for the duration, then restored byte-for-byte from the backup and diffed clean (`diff` produced no output) before deleting the backup file. Final content confirmed:
   ```
   VITE_API_URL=http://localhost:8001
   ```
3. **This report** reflects only steps actually executed against the disposable `chokmoki-dr` sandbox (mongodb:27019, redis:6381, minio:9002/9003, backend:8002) — never the real production stack with live orders/contacts/R2 data.

---

## Addendum (2026-07-10) — real browser check, dedup gap follow-up, integrity re-read

Written in a separate session from the one that ran Phases 0–7 above. The `chokmoki-dr` sandbox was still running from before (4 containers healthy, ~2h uptime at the time of this addendum); the real `chokmoki-*` stack was confirmed still `Up`/`healthy` and separate throughout. `aurum-editorial/.env.local` (top-level checkout) was untouched — already at `http://localhost:8001` from the original rehearsal's cleanup. The frontend dev server for this addendum was run from `aurum-editorial/.worktrees/content-import-restore` only, whose own `.env.local` was already pointed at the sandbox (`VITE_API_URL=http://localhost:8002`) from the original rehearsal and was left that way — **not** the top-level checkout's env file, so no restore-then-swap-back was needed against the file the instructions were protecting.

### 1. Real browser check (closing the Phase 5 gap)

The original rehearsal's `browse` skill install was still broken (same Playwright/Chromium version-mismatch symptom). Per instructions, gave it no more than the tooling budget, then fell back directly to a vanilla Playwright install (`npm install playwright` + `npx playwright install chromium`) in a scratch directory — this completed cleanly in under 3 minutes, no lock issues.

**First attempt used the wrong dev-server port (5183)** and produced CORS errors on every API call (`Access-Control-Allow-Origin` missing) — self-inflicted, not a product bug: the backend's `CORS_ALLOWED_ORIGINS` in `.env.sandbox` only allow-lists `http://localhost:5173,http://localhost:5174`. Re-ran the dev server on `--port 5174` and the CORS errors disappeared entirely.

Loaded 4 pages in a real rendered Chromium browser (1440×900), screenshotted, and checked `console` events + failed network requests on each:

| Page | URL | Console errors | Broken `<img>` (naturalWidth 0) | Screenshot |
|---|---|---|---|---|
| Storefront home | `/` | 0 | 0 | `dr-rehearsal-screenshots/home.png` |
| Product detail | `/product/ganges-pearl-drop` | 0 | 0 | `dr-rehearsal-screenshots/product-detail.png` |
| Policy | `/policy` | 0 | 0 | `dr-rehearsal-screenshots/policy.png` |
| Journal/blog | `/blog` | 0 | 0 | `dr-rehearsal-screenshots/blog-journal.png` |

There is no standalone FAQ route — the FAQ block is a section on the home page (`FAQSection` in `Home.tsx`), gated behind this codebase's scroll-triggered `LazySection` (mounts only on real `IntersectionObserver` entry, not on viewport resize). Playwright's default `fullPage` screenshot **resizes the viewport instead of scrolling**, so an initial capture attempt showed a large blank gap where the FAQ (and everything below it) should be — a real gap in how "screenshot the page" was being done, not a product bug. Re-captured after programmatically scrolling the full page height first; the FAQ section then rendered with both restored questions verbatim (`Do you offer international shipping for DR rehearsal?`, `What silver purity do you use?`) and the nav/footer labels matching the Phase 1 baseline (`DR Shop All`, `Home`, address, etc.) — see `faq-check.png`.

**Visual confirmation:** product thumbnails, category banners, and journal cover images all rendered as actual images (JPEG bytes, not `alt`-text broken-image icons) at their restored URLs. Several of these images are themselves solid-color placeholder JPEGs with an embedded label (e.g. a plain brown square captioned "Necklaces Category Thumb") — that is the real, byte-accurate content of the Phase 1 test fixtures the population script generated, confirmed by downloading and viewing the JPEG directly; it is not a rendering failure. No genuinely broken images were found on any of the 4 pages.

**One real (pre-existing, non-restore) bug found by the browser check that the original HTTP-only check could not have caught:** on the home page, `EditorialSplitSlider` (via `HomeGiftsSection`) unconditionally runs every slide's `imageSrc` through `resolveCdnUrl()` (`src/lib/cdnUrl.ts`), which only special-cases paths starting literally with `/assets/` to skip CDN-prefixing. In Vite **dev mode**, bundled local images (`import x from "@/assets/foo.webp"`) resolve to `/src/assets/foo.webp`, not `/assets/foo.webp` — so during the brief window before the real `useCollectionSlides()` data loads (or on the DEFAULT_SLIDES fallback path), those local asset requests get wrongly rewritten to `${CDN_BASE}/src/assets/foo.webp` and fail (`net::ERR_BLOCKED_BY_ORB` against the MinIO/CDN origin, since that path obviously doesn't exist there). Confirmed via direct code read (`cdnUrl.ts:15`, `EditorialSplitSlider.tsx:42`) and reproduced consistently across repeated loads. **This is unrelated to the restore feature or this rehearsal's data** — it's a latent frontend bug that only manifests in Vite dev mode (a production build's hashed `/assets/<hash>.webp` output path *would* match the `/assets/` guard and behave correctly), and it did not block rendering or produce a broken/missing image on screen — no user-visible defect, only 4 failed background requests and zero console errors. Flagging for awareness, not fixing here (out of scope for this rehearsal).

### 2. Dedup gap — confirmed non-narrower, quantified

Restored the same `dr-export.zip` a **third** time against the sandbox (now carrying Phase 1's original seed + Phase 4/6/7's two prior restores). Note: the actual restore endpoint is `POST /api/admin/import?dry_run=<bool>` with the file under form field **`bundle`** (not `file`, and `dry_run` is a query param, not a form field — the original report's curl examples were correct on this, this session just had to rediscover the exact wire shape via `/openapi.json` after a couple of `422`s).

Real confirm response (run 3), verbatim: identical shape to runs 1/2 — `"assets_restored":24,"assets_failed":0,"assets_deduplicated":3`.

`kolkata-kantha-choker` thumbnail URL across all three runs:
- Run 1: `.../restored/229fe97370b44ccc927ab515c0538989.jpg`
- Run 2: `.../restored/4c14a81613854fdeb1433ec3a0da502a.jpg`
- Run 3: `.../restored/e5f0f5945388408b95b704f5a54e1ffb.jpg`

All three URLs are **distinct** — confirms this is genuinely "new URL every time," not something that narrows or stabilizes after the first re-restore. `sha256` of the run-3 object was re-checked directly: `17c11a4dc76e68217624b11233b6d053e71e39db403dd7740ce5696704afe6cf` — identical to the Phase 1 baseline and to runs 1/2, so content fidelity still holds; only the object key churns.

**Concrete cost, measured directly against the MinIO bucket:**
- Object count immediately before this addendum's run 3: **64** objects under `dr-rehearsal-sandbox` (all but one stray Phase-0 health-check object live under the `chokmoki-dr/restored/` prefix).
- Object count immediately after run 3: **85** objects.
- Delta: **+21** — exactly `assets_restored (24) − assets_deduplicated (3)`, i.e. every single restore of this same 24-asset export permanently adds 21 brand-new, orphaned duplicate objects to the bucket. Nothing from any prior run is ever reclaimed or reused. At this rate, N restores of the same export leave roughly `N × 21` duplicate objects sitting in the bucket forever (on top of the Phase 1 seed uploads), with no cleanup path.

This does not change the original finding's verdict — it sharpens it: the gap is confirmed to compound linearly and indefinitely across repeated restores, not just a one-time "restore twice" artifact.

### 3. Integrity re-read of the original report

This addendum was written in a new session, so it does not have access to this conversation's original raw terminal output to line-by-line diff against — only the report text itself and independent spot-checks against the sandbox's *current* state (which reflects Phase 1 seed + Phases 4/6/7's restores + this addendum's own run 3, i.e. it is not a clean re-run of the original rehearsal). With that caveat, this addendum:

- Re-ran the same 19-collection count query against the sandbox right now: all counts (3 products, 2 categories, 2 hero_configs, ..., 2 blog_posts) match the Phase 1 baseline table in the report exactly, still holding after two additional restores since the report was written — consistent with, though not a substitute for, the report's own Phase 5/6 doc-count-diff claims.
- Confirmed the real `chokmoki-*` stack is still up, healthy, and separate from `chokmoki-dr-*` — consistent with the report's final safety checks.
- Found nothing in the original report's phase-by-phase claims (doc counts, spot-check values, index behavior, corruption-path skip handling) that reads more confident than what the report itself documents as its evidence — the report is already careful to mark every substitution (HTTP-instead-of-browser, script-instead-of-click) and every deviation (index growth, dedup scope) explicitly rather than glossing over them. The one place this addendum's independent testing genuinely exceeds the original report's evidence is Phase 5's visual check, which is now backed by an actual rendered-browser pass instead of an HTTP proxy for it (see §1) — that gap is now closed, not just re-asserted.

**Net effect on prior verdicts:** no prior PASS is overturned. The Phase 5 asterisk (HTTP-only, not browser-verified) is resolved — real browser confirms no broken images, no console errors, correct nav/FAQ/policy/journal content. The Phase 6 dedup finding is confirmed and quantified further, still unresolved as a known issue, not yet fixed. One new, minor, out-of-scope frontend bug was found (dev-mode-only CDN URL misresolution for bundled local assets) and is noted for future attention, not acted on.

**Sandbox left running** (`chokmoki-dr-*`, all 4 containers) for further manual testing, as requested. Frontend dev server for this addendum (port 5174, from the `content-import-restore` worktree) also left running.
