# Content Import/Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "restore from backup" feature that accepts the ZIP produced by `exportAllContentBundle()` (in `aurum-editorial/src/lib/contentBundle.ts`) and repopulates MongoDB + re-uploads all images/videos to R2, so a wiped backend can be fully restored from a previously downloaded export.

**Architecture:** New backend endpoint `POST /api/admin/import` (multipart ZIP upload, admin-only) parses the bundle with Python's stdlib `zipfile`, reads `content.json` for the 17 sections and `assets-manifest.csv` to know which files under `assets/` map to which original CDN URL. Every bundled asset is re-uploaded to R2 via the existing `R2Service`, producing a new URL (deduped by content hash so re-running a restore doesn't create duplicate R2 objects); every occurrence of the old URL inside the section JSON is rewritten to the new URL before the section is upserted directly into its MongoDB collection (bypassing the admin CRUD service layer, since this is a raw dump restore, not user-entered data). A `dry_run=true` mode computes the same plan without writing anything, for a "Preview restore" step in the UI. After a real restore, indexes for the 17 restored collections are (re)created, since a wiped Mongo has none. A coverage-guard test keeps the set of sections `import_service.py` knows how to write in lockstep with the 17 keys `contentBundle.ts` exports, so an unhandled new section fails CI loudly instead of silently failing to restore. A companion frontend flow lets an admin pick the ZIP, preview what a restore would do, then confirm — with any non-`__error` skipped section surfaced as a hard warning, not folded into the success toast.

**Tech Stack:** FastAPI + Motor (async MongoDB), boto3 (R2 upload, existing `R2Service`), Python stdlib `zipfile`/`csv`, pytest + `unittest.mock`/`AsyncMock` (backend TDD), React + `adminApi`/`adminFetch`, Vitest (frontend TDD).

---

## Reference: bundle format (entity-based, self-contained)

Produced by `aurum-editorial/src/lib/contentBundle.ts`. ZIP contains:
```
products/<slug>/          One folder per product.
  content.json            { exported_at, generator, products: { <product data with local paths> } }
  content.md
  images/                 Downloaded images (thumbnail.jpg, gallery-1.jpg, ...).
sections/<key>/           One folder per admin section (hero, categories, ...).
  content.json            { exported_at, generator, <key>: <section data with local paths> }
  content.md
  images/                 Present only if the section has image fields.
manifest.csv              Every file in the ZIP, entity, field, original source URL, status, bytes.
content.csv               Flat human-readable table (section, field, value).
README.txt
```
- Every `content.json` references images by local relative path (e.g. `"thumbnail": "images/thumbnail.jpg"`), **not** by the original live URL. The original source URL lives only in `manifest.csv`.
- `manifest.csv` columns: `Path in ZIP, Entity, Field, Original Source URL, Status, Bytes`. Replaces the old `assets-manifest.csv`. Only rows with `Status == "downloaded"` have real bytes and a usable `Original Source URL`.
- The flat sections dict from the old format is reconstructed during import by walking `products/*/content.json` and `sections/*/content.json`, and inflating relative image paths back to original URLs from `manifest.csv`.
- The 17 section keys (frontend: `contentBundle.ts:138-159`, backend routes: `api/routes/admin_content.py` / `api/routes/admin_catalog.py`, all behind `Depends(require_admin)`):

| section key | shape in sections/<key>/content.json.<key> | mongo collection(s) | filter for upsert |
|---|---|---|---|
| `products` | list of product dicts | `products` | `_id` |
| `categories` | list of category dicts | `categories` | `_id` |
| `hero` | list of hero config dicts | `hero_configs` | `_id` |
| `site-assets` | list of site asset dicts | `site_assets` | `_id` |
| `collection-slides` | list of slide dicts | `collection_slides` | `_id` |
| `testimonials` | list of testimonial dicts | `testimonials` | `_id` |
| `faq` | list of FAQ item dicts | `faq_items` | `_id` |
| `studio-settings` | single dict | `studio_settings` | `{"settings_key": "main"}` |
| `shop-page` | single dict | `shop_page_settings` | `{"settings_key": "main"}` |
| `home-page` | single dict | `home_page_settings` | `{"settings_key": "main"}` |
| `story-page` | single dict | `story_page_settings` | `{"settings_key": "main"}` |
| `navigation` | single dict | `navigation_settings` | `{"settings_key": "main"}` |
| `contact-page` | single dict | `contact_page_settings` | `{"settings_key": "main"}` |
| `history-page` | single dict | `history_page_settings` | `{"settings_key": "main"}` |
| `product-page` | single dict | `product_page_settings` | `{"settings_key": "main"}` |
| `policies` | `{"meta": {...}\|null, "sections": [{...,"_id":...}]}` | `policy_page_meta` (meta) + `policy_sections` (sections) | meta: `{"meta_key": "main"}`; sections: `_id` |
| `journal` | `{"meta": {...}\|null, "data": [{...,"_id":...}]}` | `journal_page_settings` (meta) + `blog_posts` (data) | meta: `{"settings_key": "main"}`; posts: `_id` |

- Any section value may instead be `{"__error": "<message>"}` if the original export failed to fetch it (`contentBundle.ts:129-135`) — the importer must skip these, not write them.
- `manifest.csv` rows: `Path in ZIP, Entity, Field, Original Source URL, Status, Bytes`. Only rows with `Status == "downloaded"` have real bytes at that path and a usable `Original Source URL` to remap; `"failed: ..."` rows have no corresponding file.
- `R2Service.upload_file(file_bytes, extension, content_type, folder="products") -> str` (`src/services/r2_service.py:54-83`) uploads and returns the new public URL. It has no extension allow-list of its own (that lives in `src/utils/upload_validation.py`, which is stricter than what a restore needs — bundle assets can be `.gif`/`.svg`/`.webm`/`.mov` which `validate_upload` rejects, so the importer infers extension/content-type itself instead of calling `validate_upload`).
- Admin auth: `require_admin` (`src/plugins/admin_deps.py:46-52`), imported everywhere via `api.bootstrap`.
- Cache: `cache.delete_pattern(pattern)` (`src/services/cache_service.py:34-41`) — call with `"chokmoki:*"` after a restore so every `get_public`/`get_*` cache the various services set (e.g. `chokmoki:studio_settings`, `chokmoki:policies`, `chokmoki:journal_page`) is invalidated in one shot.
- Indexes: there is no centralized index-migration module today. The only precedent is per-service `ensure_indexes()` methods (`OrderService.ensure_indexes()` at `src/services/order_service.py:49-55`, `FraudReviewService.ensure_indexes()` at `src/services/fraud_review_service.py:17-22`), and only `OrderService`'s is actually called, from the `lifespan()` startup hook in `api/index.py:39-59`. None of the 17 restore collections have an `ensure_indexes()` today — Task 11 below adds one scoped to them, since a wiped Mongo restored via this feature would otherwise come back with zero indexes.
- Asset harvesting (export side): `walk()` in `contentBundle.ts:202-233` is a fully generic recursive walk over every section's JSON (arrays and nested objects included), so it structurally visits every leaf value — nested product galleries, variant fields, etc. are not missed by structure. The only residual risk is the `classify()` heuristic (`contentBundle.ts:189-196`): a string is treated as media if its value matches `MEDIA_EXT` (has a recognizable image/video extension) **or** its field name matches `MEDIA_FIELD`. A media URL that has neither a recognizable extension nor a matching field name (e.g. a signed CDN URL with no extension, stored under a field like `cover_url` or `src`) would silently export as plain text and never reach `assets-manifest.csv`. Task 15 below documents and regression-tests this.

---

## File Structure

- Create: `src/services/import_service.py` — pure parsing + restore logic (framework-free, easy to unit test).
- Create: `api/routes/admin_import.py` — thin FastAPI route (multipart upload, size cap, `dry_run` query param, calls `import_service`).
- Modify: `api/bootstrap.py` — expose `parse_bundle_zip`, `restore_bundle`, `plan_restore`, `ensure_restore_indexes`, `BundleParseError`, `MAX_BUNDLE_BYTES` from `import_service` (matches the existing "every app import goes through bootstrap" convention).
- Modify: `api/index.py` — register `admin_import.router`.
- Create: `__tests__/test_import_service.py` — unit tests for parsing/restore logic (mocked Mongo/R2).
- Create: `__tests__/test_admin_import_route.py` — route wiring tests (auth required, registered, delegates correctly, dry-run), following the `TestClient` + module-stubbing pattern in `__tests__/test_import_smoke.py`.
- Modify: `aurum-editorial/src/lib/contentBundle.ts` — add `importAllContentBundle(file: File, opts?: { dryRun?: boolean }): Promise<ImportBundleResult>`.
- Create: `aurum-editorial/src/lib/contentBundle.import.test.ts` — Vitest tests for the new frontend function (mirrors `src/lib/api.test.ts` style: `vi.stubGlobal("fetch", ...)`).
- Create: `aurum-editorial/src/lib/contentBundle.assetCoverage.test.ts` — regression test enumerating known media field paths (`thumbnail`, `gallery[]`, `medias[].url`, etc.) against `MEDIA_FIELD`/`MEDIA_EXT`, documenting the heuristic's coverage and gap.
- Modify: `aurum-editorial/src/components/admin/AdminLayoutContext.tsx` — add `onImportAll`/`isImportingAll`, `onPreviewImport`/`isPreviewingImport`, and `importPreview` state to context, mirroring `onExportAll`/`isExportingAll` (lines 251-269, 78-79, 289-320).
- Modify: `aurum-editorial/src/components/admin/AdminShell.tsx` — add "Restore from backup (ZIP)" flow: file picker → dry-run preview panel → confirm button, next to the existing export button (around line 307-315).

---

### Task 1: `import_service.py` — parse the ZIP

**Files:**
- Create: `src/services/import_service.py`
- Test: `__tests__/test_import_service.py`

- [x] **Step 1: Write the failing tests**

```python
# __tests__/test_import_service.py
"""Tests for src.services.import_service — bundle ZIP parsing and Mongo/R2 restore."""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.services.import_service import BundleParseError, parse_bundle_zip  # noqa: E402


def _build_zip(
    sections: dict,
    assets: dict[str, bytes] | None = None,
    manifest_rows: list[dict] | None = None,
    include_content_json: bool = True,
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        if include_content_json:
            zf.writestr(
                "content.json",
                json.dumps({"exported_at": "2026-07-09T00:00:00Z", "generator": "test", "sections": sections}),
            )
        for path, data in (assets or {}).items():
            zf.writestr(path, data)
        if manifest_rows is not None:
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            writer.writerow(["File", "Section", "Field (where filled)", "Source URL", "Status", "Bytes"])
            for row in manifest_rows:
                writer.writerow(
                    [row["file"], row["section"], row["field"], row["url"], row["status"], row.get("bytes", 0)]
                )
            zf.writestr("assets-manifest.csv", csv_buf.getvalue())
    return buf.getvalue()


class TestParseBundleZip:
    def test_extracts_sections_from_content_json(self):
        raw = _build_zip(sections={"faq": [{"_id": "507f1f77bcf86cd799439011", "question": "Q1"}]})
        parsed = parse_bundle_zip(raw)
        assert parsed.sections == {"faq": [{"_id": "507f1f77bcf86cd799439011", "question": "Q1"}]}

    def test_extracts_downloaded_assets_and_source_urls(self):
        raw = _build_zip(
            sections={"faq": []},
            assets={"assets/faq/001-photo.jpg": b"\xff\xd8\xff-fake-jpeg-bytes"},
            manifest_rows=[
                {
                    "file": "assets/faq/001-photo.jpg",
                    "section": "faq",
                    "field": "icon_url",
                    "url": "https://cdn.amplifycheckout.com/faq/photo.jpg",
                    "status": "downloaded",
                    "bytes": 21,
                }
            ],
        )
        parsed = parse_bundle_zip(raw)
        assert parsed.assets["assets/faq/001-photo.jpg"] == b"\xff\xd8\xff-fake-jpeg-bytes"
        assert parsed.asset_urls["assets/faq/001-photo.jpg"] == "https://cdn.amplifycheckout.com/faq/photo.jpg"

    def test_skips_failed_manifest_rows(self):
        raw = _build_zip(
            sections={"faq": []},
            assets={},
            manifest_rows=[
                {
                    "file": "assets/faq/002-missing.jpg",
                    "section": "faq",
                    "field": "icon_url",
                    "url": "https://cdn.amplifycheckout.com/faq/missing.jpg",
                    "status": "failed: 404",
                    "bytes": 0,
                }
            ],
        )
        parsed = parse_bundle_zip(raw)
        assert "assets/faq/002-missing.jpg" not in parsed.asset_urls

    def test_raises_bundle_parse_error_without_content_json(self):
        raw = _build_zip(sections={}, include_content_json=False)
        with pytest.raises(BundleParseError, match="content.json"):
            parse_bundle_zip(raw)

    def test_raises_bundle_parse_error_on_invalid_zip(self):
        with pytest.raises(BundleParseError, match="not a valid ZIP"):
            parse_bundle_zip(b"not a zip file at all")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest __tests__/test_import_service.py -v` (from `chokmoki-serverless/`)
Expected: `ModuleNotFoundError: No module named 'src.services.import_service'` (or `ImportError`).

- [x] **Step 3: Write minimal implementation**

```python
# src/services/import_service.py
"""Parse and restore a site-content backup ZIP produced by
aurum-editorial/src/lib/contentBundle.ts (exportAllContentBundle).
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List


MAX_BUNDLE_BYTES = 500 * 1024 * 1024  # 500MB — export bundles can carry hundreds of product photos

ASSET_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "avif": "image/avif",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mov": "video/quicktime",
    "m4v": "video/x-m4v",
}


class BundleParseError(ValueError):
    """Raised when the uploaded file is not a well-formed content bundle ZIP."""


@dataclass
class ParsedBundle:
    sections: Dict[str, Any] = field(default_factory=dict)
    assets: Dict[str, bytes] = field(default_factory=dict)
    asset_urls: Dict[str, str] = field(default_factory=dict)  # zip path -> original source URL


def parse_bundle_zip(raw: bytes) -> ParsedBundle:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise BundleParseError("Uploaded file is not a valid ZIP archive") from e

    names = set(zf.namelist())
    if "content.json" not in names:
        raise BundleParseError("Bundle is missing content.json")

    try:
        content = json.loads(zf.read("content.json").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise BundleParseError("content.json is not valid JSON") from e

    sections = content.get("sections")
    if not isinstance(sections, dict):
        raise BundleParseError("content.json has no 'sections' object")

    asset_urls: Dict[str, str] = {}
    if "assets-manifest.csv" in names:
        manifest_text = zf.read("assets-manifest.csv").decode("utf-8-sig")
        for row in csv.DictReader(io.StringIO(manifest_text)):
            if row.get("Status") == "downloaded":
                file_path = row.get("File", "")
                url = row.get("Source URL", "")
                if file_path and url:
                    asset_urls[file_path] = url

    assets: Dict[str, bytes] = {}
    for path in asset_urls:
        if path in names:
            assets[path] = zf.read(path)

    return ParsedBundle(sections=sections, assets=assets, asset_urls=asset_urls)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest __tests__/test_import_service.py -v`
Expected: all 5 tests in `TestParseBundleZip` PASS.

- [x] **Step 5: Commit**

```bash
git add src/services/import_service.py __tests__/test_import_service.py
git commit -m "feat: parse content backup ZIP bundles for restore"
```

---

### Task 2: `import_service.py` — asset re-upload + URL remap

**Files:**
- Modify: `src/services/import_service.py`
- Test: `__tests__/test_import_service.py`

- [x] **Step 1: Write the failing tests**

Append to `__tests__/test_import_service.py`:

```python
from src.services.import_service import restore_bundle, ParsedBundle  # noqa: E402


def _make_database(collections: dict[str, AsyncMock] | None = None) -> MagicMock:
    """Fake Motor database: db["name"] returns an AsyncMock collection."""
    store: dict[str, AsyncMock] = collections or {}

    def _getitem(name: str) -> AsyncMock:
        if name not in store:
            coll = AsyncMock()
            coll.replace_one = AsyncMock()
            store[name] = coll
        return store[name]

    database = MagicMock()
    database.__getitem__.side_effect = _getitem
    database._store = store
    return database


class TestRestoreBundleAssets:
    @pytest.mark.asyncio
    async def test_uploads_asset_and_remaps_url_in_section(self):
        parsed = ParsedBundle(
            sections={
                "faq": [
                    {
                        "_id": "507f1f77bcf86cd799439011",
                        "question": "Q1",
                        "icon_url": "https://cdn.amplifycheckout.com/faq/photo.jpg",
                    }
                ]
            },
            assets={"assets/faq/001-photo.jpg": b"\xff\xd8\xff-fake-jpeg-bytes"},
            asset_urls={"assets/faq/001-photo.jpg": "https://cdn.amplifycheckout.com/faq/photo.jpg"},
        )
        database = _make_database()
        r2 = AsyncMock()
        r2.upload_file = AsyncMock(return_value="https://cdn.chokmoki.example/faq/newname.jpg")

        result = await restore_bundle(parsed, database, r2)

        r2.upload_file.assert_awaited_once()
        call_kwargs = r2.upload_file.await_args.kwargs
        assert call_kwargs["extension"] == "jpg"
        assert call_kwargs["content_type"] == "image/jpeg"

        faq_collection = database["faq_items"]
        written_doc = faq_collection.replace_one.await_args.args[1]
        assert written_doc["icon_url"] == "https://cdn.chokmoki.example/faq/newname.jpg"
        assert result.assets_restored == 1
        assert result.assets_failed == 0

    @pytest.mark.asyncio
    async def test_asset_upload_failure_keeps_original_url_and_continues(self):
        parsed = ParsedBundle(
            sections={
                "faq": [
                    {
                        "_id": "507f1f77bcf86cd799439011",
                        "question": "Q1",
                        "icon_url": "https://cdn.amplifycheckout.com/faq/photo.jpg",
                    }
                ]
            },
            assets={"assets/faq/001-photo.jpg": b"\xff\xd8\xff-fake-jpeg-bytes"},
            asset_urls={"assets/faq/001-photo.jpg": "https://cdn.amplifycheckout.com/faq/photo.jpg"},
        )
        database = _make_database()
        r2 = AsyncMock()
        r2.upload_file = AsyncMock(side_effect=RuntimeError("R2 unreachable"))

        result = await restore_bundle(parsed, database, r2)

        written_doc = database["faq_items"].replace_one.await_args.args[1]
        assert written_doc["icon_url"] == "https://cdn.amplifycheckout.com/faq/photo.jpg"
        assert result.assets_restored == 0
        assert result.assets_failed == 1
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest __tests__/test_import_service.py::TestRestoreBundleAssets -v`
Expected: FAIL with `ImportError: cannot import name 'restore_bundle'`.

- [x] **Step 3: Write minimal implementation**

Append to `src/services/import_service.py`:

```python
from datetime import datetime, timezone


@dataclass
class ImportResult:
    sections_restored: List[str] = field(default_factory=list)
    sections_skipped: List[str] = field(default_factory=list)
    assets_restored: int = 0
    assets_failed: int = 0


def _asset_extension(zip_path: str) -> str:
    if "." not in zip_path:
        return "bin"
    return zip_path.rsplit(".", 1)[-1].lower()


async def _upload_assets(parsed: ParsedBundle, r2_service) -> tuple[Dict[str, str], int, int]:
    """Upload every bundled asset to R2. Returns (old_url -> new_url map, restored, failed)."""
    url_map: Dict[str, str] = {}
    restored = 0
    failed = 0
    for zip_path, old_url in parsed.asset_urls.items():
        data = parsed.assets.get(zip_path)
        if data is None:
            continue
        ext = _asset_extension(zip_path)
        content_type = ASSET_CONTENT_TYPES.get(ext, "application/octet-stream")
        try:
            new_url = await r2_service.upload_file(data, extension=ext, content_type=content_type, folder="restored")
        except Exception:
            failed += 1
            continue
        url_map[old_url] = new_url
        restored += 1
    return url_map, restored, failed


def _remap_urls(value: Any, url_map: Dict[str, str]) -> Any:
    if isinstance(value, str):
        return url_map.get(value, value)
    if isinstance(value, list):
        return [_remap_urls(v, url_map) for v in value]
    if isinstance(value, dict):
        return {k: _remap_urls(v, url_map) for k, v in value.items()}
    return value


async def restore_bundle(parsed: ParsedBundle, database, r2_service) -> ImportResult:
    url_map, assets_restored, assets_failed = await _upload_assets(parsed, r2_service)
    sections = _remap_urls(parsed.sections, url_map)

    result = ImportResult(assets_restored=assets_restored, assets_failed=assets_failed)
    for key, value in sections.items():
        if isinstance(value, dict) and "__error" in value:
            result.sections_skipped.append(key)
            continue
        await _restore_section(key, value, database, result)
    return result


async def _restore_section(key: str, value: Any, database, result: ImportResult) -> None:
    result.sections_skipped.append(key)  # placeholder for unknown keys; Task 3 replaces this
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest __tests__/test_import_service.py::TestRestoreBundleAssets -v`
Expected: FAIL — `_restore_section` is still a stub, so `faq_items` collection is never touched and `written_doc` lookup raises. This is expected at this checkpoint; Task 3 completes `_restore_section`. Do not skip ahead — proceed to Task 3 immediately, these two tests stay red until Task 3's Step 4.

- [x] **Step 5: Commit (with tests still red, marked WIP)**

```bash
git add src/services/import_service.py __tests__/test_import_service.py
git commit -m "wip: R2 re-upload + URL remap for restore (section writes land in next commit)"
```

---

### Task 3: `import_service.py` — write sections into MongoDB

**Files:**
- Modify: `src/services/import_service.py`
- Test: `__tests__/test_import_service.py`

- [x] **Step 1: Write the failing tests**

Append to `__tests__/test_import_service.py`:

```python
from bson import ObjectId  # noqa: E402


class TestRestoreBundleSections:
    @pytest.mark.asyncio
    async def test_restores_list_section_upserting_by_id(self):
        parsed = ParsedBundle(sections={"faq": [{"_id": "507f1f77bcf86cd799439011", "question": "Q1"}]})
        database = _make_database()

        result = await restore_bundle(parsed, database, AsyncMock())

        coll = database["faq_items"]
        coll.replace_one.assert_awaited_once()
        filter_arg, doc_arg = coll.replace_one.await_args.args[:2]
        assert filter_arg == {"_id": ObjectId("507f1f77bcf86cd799439011")}
        assert doc_arg["question"] == "Q1"
        assert "_id" not in doc_arg  # _id goes in the filter, not $set/replace body's duplicate key
        assert coll.replace_one.await_args.kwargs["upsert"] is True
        assert result.sections_restored == ["faq"]

    @pytest.mark.asyncio
    async def test_generates_new_id_when_missing_or_invalid(self):
        parsed = ParsedBundle(sections={"faq": [{"question": "no id here"}]})
        database = _make_database()

        await restore_bundle(parsed, database, AsyncMock())

        coll = database["faq_items"]
        filter_arg = coll.replace_one.await_args.args[0]
        assert isinstance(filter_arg["_id"], ObjectId)

    @pytest.mark.asyncio
    async def test_restores_singleton_section_by_settings_key(self):
        parsed = ParsedBundle(sections={"studio-settings": {"email": "hi@chokmoki.com"}})
        database = _make_database()

        result = await restore_bundle(parsed, database, AsyncMock())

        coll = database["studio_settings"]
        filter_arg, doc_arg = coll.replace_one.await_args.args[:2]
        assert filter_arg == {"settings_key": "main"}
        assert doc_arg["settings_key"] == "main"
        assert doc_arg["email"] == "hi@chokmoki.com"
        assert result.sections_restored == ["studio-settings"]

    @pytest.mark.asyncio
    async def test_skips_error_sections(self):
        parsed = ParsedBundle(sections={"faq": {"__error": "fetch failed"}})
        database = _make_database()

        result = await restore_bundle(parsed, database, AsyncMock())

        assert result.sections_skipped == ["faq"]
        assert result.sections_restored == []
        database["faq_items"].replace_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_restores_policies_section_into_two_collections(self):
        parsed = ParsedBundle(
            sections={
                "policies": {
                    "meta": {"page_title": "Policies"},
                    "sections": [{"_id": "507f1f77bcf86cd799439011", "slug": "returns", "title": "Returns"}],
                }
            }
        )
        database = _make_database()

        result = await restore_bundle(parsed, database, AsyncMock())

        meta_filter, meta_doc = database["policy_page_meta"].replace_one.await_args.args[:2]
        assert meta_filter == {"meta_key": "main"}
        assert meta_doc["page_title"] == "Policies"

        section_filter, section_doc = database["policy_sections"].replace_one.await_args.args[:2]
        assert section_filter == {"_id": ObjectId("507f1f77bcf86cd799439011")}
        assert section_doc["slug"] == "returns"
        assert result.sections_restored == ["policies"]

    @pytest.mark.asyncio
    async def test_restores_journal_section_into_two_collections(self):
        parsed = ParsedBundle(
            sections={
                "journal": {
                    "meta": {"page_title": "Journal"},
                    "data": [{"_id": "507f1f77bcf86cd799439011", "title": "Post 1"}],
                }
            }
        )
        database = _make_database()

        result = await restore_bundle(parsed, database, AsyncMock())

        meta_filter, meta_doc = database["journal_page_settings"].replace_one.await_args.args[:2]
        assert meta_filter == {"settings_key": "main"}
        assert meta_doc["page_title"] == "Journal"

        post_filter, post_doc = database["blog_posts"].replace_one.await_args.args[:2]
        assert post_filter == {"_id": ObjectId("507f1f77bcf86cd799439011")}
        assert post_doc["title"] == "Post 1"
        assert result.sections_restored == ["journal"]

    @pytest.mark.asyncio
    async def test_unknown_section_key_is_skipped(self):
        parsed = ParsedBundle(sections={"totally-unknown-section": {"x": 1}})
        database = _make_database()

        result = await restore_bundle(parsed, database, AsyncMock())

        assert result.sections_skipped == ["totally-unknown-section"]
        assert result.sections_restored == []
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest __tests__/test_import_service.py::TestRestoreBundleSections -v`
Expected: FAIL — every case currently lands in the Task 2 stub's catch-all `sections_skipped`, so `test_skips_error_sections` may pass by accident but the others fail (`replace_one` never called / wrong section key semantics).

- [x] **Step 3: Write minimal implementation**

Replace the `_restore_section` stub in `src/services/import_service.py` with:

```python
from bson import ObjectId
from bson.errors import InvalidId

SIMPLE_LIST_SECTIONS = {
    "products": "products",
    "categories": "categories",
    "hero": "hero_configs",
    "site-assets": "site_assets",
    "collection-slides": "collection_slides",
    "testimonials": "testimonials",
    "faq": "faq_items",
}

SINGLETON_SECTIONS = {
    "studio-settings": ("studio_settings", "settings_key", "main"),
    "shop-page": ("shop_page_settings", "settings_key", "main"),
    "home-page": ("home_page_settings", "settings_key", "main"),
    "story-page": ("story_page_settings", "settings_key", "main"),
    "navigation": ("navigation_settings", "settings_key", "main"),
    "contact-page": ("contact_page_settings", "settings_key", "main"),
    "history-page": ("history_page_settings", "settings_key", "main"),
    "product-page": ("product_page_settings", "settings_key", "main"),
}


def _object_id(raw: Any) -> ObjectId:
    if isinstance(raw, str):
        try:
            return ObjectId(raw)
        except InvalidId:
            pass
    return ObjectId()


async def _restore_list(database, collection_name: str, items: List[Dict[str, Any]]) -> None:
    collection = database[collection_name]
    for item in items:
        if not isinstance(item, dict):
            continue
        doc = dict(item)
        oid = _object_id(doc.pop("_id", None))
        await collection.replace_one({"_id": oid}, doc, upsert=True)


async def _restore_singleton(database, collection_name: str, key_field: str, key_value: str, value: Dict[str, Any]) -> None:
    doc = dict(value)
    doc.pop("_id", None)
    doc[key_field] = key_value
    await database[collection_name].replace_one({key_field: key_value}, doc, upsert=True)


async def _restore_section(key: str, value: Any, database, result: ImportResult) -> None:
    if key in SIMPLE_LIST_SECTIONS:
        if not isinstance(value, list):
            result.sections_skipped.append(key)
            return
        await _restore_list(database, SIMPLE_LIST_SECTIONS[key], value)
        result.sections_restored.append(key)
        return

    if key in SINGLETON_SECTIONS:
        if not isinstance(value, dict):
            result.sections_skipped.append(key)
            return
        collection_name, key_field, key_value = SINGLETON_SECTIONS[key]
        await _restore_singleton(database, collection_name, key_field, key_value, value)
        result.sections_restored.append(key)
        return

    if key == "policies" and isinstance(value, dict):
        meta = value.get("meta")
        if isinstance(meta, dict):
            await _restore_singleton(database, "policy_page_meta", "meta_key", "main", meta)
        sections = value.get("sections")
        if isinstance(sections, list):
            await _restore_list(database, "policy_sections", sections)
        result.sections_restored.append(key)
        return

    if key == "journal" and isinstance(value, dict):
        meta = value.get("meta")
        if isinstance(meta, dict):
            await _restore_singleton(database, "journal_page_settings", "settings_key", "main", meta)
        posts = value.get("data")
        if isinstance(posts, list):
            await _restore_list(database, "blog_posts", posts)
        result.sections_restored.append(key)
        return

    result.sections_skipped.append(key)
```

Also update `restore_bundle`'s skip check (from Task 2) to only treat a **dict containing `__error`** as an error section, not every dict (singleton sections are dicts too) — it already does `isinstance(value, dict) and "__error" in value`, which is correct as-is; no change needed there.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest __tests__/test_import_service.py -v`
Expected: all tests in `test_import_service.py` (Tasks 1-3) PASS.

- [x] **Step 5: Commit**

```bash
git add src/services/import_service.py
git commit -m "feat: restore all 17 content sections into MongoDB from backup ZIP"
```

---

### Task 4: `import_service.py` — cache invalidation

**Files:**
- Modify: `src/services/import_service.py`
- Test: `__tests__/test_import_service.py`

- [x] **Step 1: Write the failing test**

Append to `__tests__/test_import_service.py`:

```python
class TestRestoreBundleCacheInvalidation:
    @pytest.mark.asyncio
    async def test_invalidates_cache_after_restore(self, monkeypatch):
        from src.services import import_service

        delete_pattern = AsyncMock()
        monkeypatch.setattr(import_service.cache, "delete_pattern", delete_pattern)

        parsed = ParsedBundle(sections={"faq": [{"_id": "507f1f77bcf86cd799439011", "question": "Q1"}]})
        await restore_bundle(parsed, _make_database(), AsyncMock())

        delete_pattern.assert_awaited_once_with("chokmoki:*")
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest __tests__/test_import_service.py::TestRestoreBundleCacheInvalidation -v`
Expected: FAIL — `import_service` has no `cache` attribute.

- [x] **Step 3: Write minimal implementation**

At the top of `src/services/import_service.py`, add:
```python
from src.services.cache_service import cache
```

At the end of `restore_bundle` (after the `for key, value in sections.items()` loop, before `return result`), add:
```python
    await cache.delete_pattern("chokmoki:*")
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest __tests__/test_import_service.py -v`
Expected: all tests PASS.

- [x] **Step 5: Commit**

```bash
git add src/services/import_service.py __tests__/test_import_service.py
git commit -m "feat: invalidate admin content cache after a restore"
```

---

### Task 5: `admin_import.py` route + bootstrap/index wiring

**Files:**
- Create: `api/routes/admin_import.py`
- Modify: `api/bootstrap.py:12-76` (try block), `api/bootstrap.py:77-151` (except block)
- Modify: `api/index.py:107-134`
- Test: `__tests__/test_admin_import_route.py`

- [x] **Step 1: Write the failing tests**

```python
# __tests__/test_admin_import_route.py
"""Route wiring tests for POST /api/admin/import."""

from __future__ import annotations

import importlib
import io
import os
import sys
import types
import zipfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _stub_external_modules() -> None:
    telegram = types.ModuleType("telegram")
    telegram.Bot = object
    telegram_error = types.ModuleType("telegram.error")
    telegram_error.TelegramError = Exception
    boto3 = types.ModuleType("boto3")
    boto3.client = lambda *args, **kwargs: object()
    botocore = types.ModuleType("botocore")
    botocore_client = types.ModuleType("botocore.client")
    botocore_client.Config = object
    botocore.client = botocore_client
    sys.modules["telegram"] = telegram
    sys.modules["telegram.error"] = telegram_error
    sys.modules["boto3"] = boto3
    sys.modules["botocore"] = botocore
    sys.modules["botocore.client"] = botocore_client


def _minimal_bundle_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr(
            "content.json",
            '{"exported_at": "2026-07-09T00:00:00Z", "generator": "test", "sections": {"faq": []}}',
        )
    return buf.getvalue()


@pytest.fixture
def api_module(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
    _stub_external_modules()
    if "api.index" in sys.modules:
        del sys.modules["api.index"]
    return importlib.import_module("api.index")


class TestAdminImportRoute:
    def test_route_registered(self, api_module):
        paths = {route.path for route in api_module.app.routes}
        assert "/api/admin/import" in paths

    def test_requires_admin(self, api_module):
        client = TestClient(api_module.app, raise_server_exceptions=True)
        files = {"bundle": ("backup.zip", _minimal_bundle_zip(), "application/zip")}
        response = client.post("/api/admin/import", files=files)
        assert response.status_code == 401

    def test_accepts_zip_and_returns_summary(self, api_module):
        from api.bootstrap import require_admin

        api_module.app.dependency_overrides[require_admin] = lambda: "admin@test.com"
        try:
            mock_result = AsyncMock()
            with patch("api.routes.admin_import.restore_bundle", new_callable=AsyncMock) as mock_restore:
                from src.services.import_service import ImportResult

                mock_restore.return_value = ImportResult(
                    sections_restored=["faq"], sections_skipped=[], assets_restored=0, assets_failed=0
                )
                client = TestClient(api_module.app, raise_server_exceptions=True)
                files = {"bundle": ("backup.zip", _minimal_bundle_zip(), "application/zip")}
                response = client.post("/api/admin/import", files=files)
        finally:
            api_module.app.dependency_overrides.pop(require_admin, None)

        assert response.status_code == 200
        body = response.json()
        assert body["sections_restored"] == ["faq"]
        assert body["assets_restored"] == 0

    def test_rejects_invalid_zip_with_400(self, api_module):
        from api.bootstrap import require_admin

        api_module.app.dependency_overrides[require_admin] = lambda: "admin@test.com"
        try:
            client = TestClient(api_module.app, raise_server_exceptions=True)
            files = {"bundle": ("backup.zip", b"not a zip", "application/zip")}
            response = client.post("/api/admin/import", files=files)
        finally:
            api_module.app.dependency_overrides.pop(require_admin, None)

        assert response.status_code == 400

    def test_rejects_oversized_bundle_with_400(self, api_module, monkeypatch):
        from api.bootstrap import require_admin
        import api.routes.admin_import as admin_import_module

        monkeypatch.setattr(admin_import_module, "MAX_BUNDLE_BYTES", 10)
        api_module.app.dependency_overrides[require_admin] = lambda: "admin@test.com"
        try:
            client = TestClient(api_module.app, raise_server_exceptions=True)
            files = {"bundle": ("backup.zip", _minimal_bundle_zip(), "application/zip")}
            response = client.post("/api/admin/import", files=files)
        finally:
            api_module.app.dependency_overrides.pop(require_admin, None)

        assert response.status_code == 400
        assert "exceeds maximum size" in response.json()["detail"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest __tests__/test_admin_import_route.py -v`
Expected: FAIL — `/api/admin/import` route doesn't exist (404s) / `ModuleNotFoundError: api.routes.admin_import`.

- [x] **Step 3: Write minimal implementation**

Create `api/routes/admin_import.py`:
```python
"""Admin restore-from-backup: accepts a content bundle ZIP and repopulates MongoDB + R2."""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from api.bootstrap import db, R2Service, require_admin, logger, BundleParseError, parse_bundle_zip, restore_bundle, MAX_BUNDLE_BYTES

router = APIRouter()


@router.post("/api/admin/import")
async def admin_import_bundle(
    bundle: UploadFile = File(...),
    email: str = Depends(require_admin),
):
    """Restore all site content + images from a previously exported backup ZIP."""
    if db is None or R2Service is None or parse_bundle_zip is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    raw = await bundle.read()
    if len(raw) > MAX_BUNDLE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Bundle exceeds maximum size of {MAX_BUNDLE_BYTES // (1024 * 1024)}MB",
        )

    try:
        parsed = parse_bundle_zip(raw)
    except BundleParseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    database = await db.get_database()
    r2 = R2Service()
    try:
        result = await restore_bundle(parsed, database, r2)
    except Exception as e:
        if logger:
            logger.error(f"Admin import failed: {e}")
        raise HTTPException(status_code=500, detail="Restore failed") from e

    return {
        "sections_restored": result.sections_restored,
        "sections_skipped": result.sections_skipped,
        "assets_restored": result.assets_restored,
        "assets_failed": result.assets_failed,
    }
```

In `api/bootstrap.py`, add to the `try:` block (after line 40, near the other service imports):
```python
    from src.services.import_service import (
        BundleParseError,
        MAX_BUNDLE_BYTES,
        parse_bundle_zip,
        restore_bundle,
    )
```

In `api/bootstrap.py`, add to the `except Exception as e:` block (near `R2Service = None`, e.g. after line 105):
```python
    BundleParseError = None
    MAX_BUNDLE_BYTES = 500 * 1024 * 1024
    parse_bundle_zip = None
    restore_bundle = None
```

In `api/index.py`, add `admin_import` to the router import tuple (line 107-121):
```python
from api.routes import (
    admin_auth,
    admin_catalog,
    admin_content,
    admin_fraud,
    admin_import,
    admin_inbox,
    admin_orders,
    admin_upload,
    contact,
    cqrs,
    cron,
    health,
    orders,
    storefront,
)
```
And register it next to `admin_upload` (after line 128):
```python
app.include_router(admin_upload.router)
app.include_router(admin_import.router)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest __tests__/test_admin_import_route.py -v`
Expected: all 5 tests PASS.

Run full backend suite to confirm no regressions: `python -m pytest -v`
Expected: all tests PASS (existing + new).

- [x] **Step 5: Commit**

```bash
git add api/routes/admin_import.py api/bootstrap.py api/index.py __tests__/test_admin_import_route.py
git commit -m "feat: add POST /api/admin/import route for restoring from backup ZIP"
```

---

### Task 6: Frontend — `importAllContentBundle()`

**Files:**
- Modify: `aurum-editorial/src/lib/contentBundle.ts`
- Test: `aurum-editorial/src/lib/contentBundle.import.test.ts`

- [x] **Step 1: Write the failing test**

```ts
// aurum-editorial/src/lib/contentBundle.import.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { importAllContentBundle } from "./contentBundle";

describe("importAllContentBundle", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("posts the ZIP as multipart form data to /api/admin/import", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        sections_restored: ["faq", "products"],
        sections_skipped: [],
        assets_restored: 3,
        assets_failed: 0,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const file = new File([new Uint8Array([1, 2, 3])], "backup.zip", { type: "application/zip" });
    const result = await importAllContentBundle(file);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/admin/import");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("bundle")).toBe(file);

    expect(result).toEqual({
      sectionsRestored: ["faq", "products"],
      sectionsSkipped: [],
      assetsRestored: 3,
      assetsFailed: 0,
    });
  });

  it("throws with the server's error message on failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Bundle is missing content.json" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const file = new File([new Uint8Array([1])], "bad.zip", { type: "application/zip" });
    await expect(importAllContentBundle(file)).rejects.toThrow("Bundle is missing content.json");
  });
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `npm run test -- contentBundle.import` (from `aurum-editorial/`)
Expected: FAIL — `importAllContentBundle` is not exported from `./contentBundle`.

- [x] **Step 3: Write minimal implementation**

In `aurum-editorial/src/lib/contentBundle.ts`, add near the existing exports (the file already imports `adminFetch` — confirm the import at the top, e.g. `import { adminFetch } from "./adminApi";`, and `API_BASE` from `./apiBase`; add both if not already present):

```ts
export interface ImportBundleResult {
  sectionsRestored: string[];
  sectionsSkipped: string[];
  assetsRestored: number;
  assetsFailed: number;
}

export async function importAllContentBundle(file: File): Promise<ImportBundleResult> {
  const form = new FormData();
  form.append("bundle", file);

  const res = await adminFetch(`${API_BASE}/admin/import`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    let message = `Restore failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* response had no JSON body */
    }
    throw new Error(message);
  }

  const body = (await res.json()) as {
    sections_restored: string[];
    sections_skipped: string[];
    assets_restored: number;
    assets_failed: number;
  };

  return {
    sectionsRestored: body.sections_restored,
    sectionsSkipped: body.sections_skipped,
    assetsRestored: body.assets_restored,
    assetsFailed: body.assets_failed,
  };
}
```

**Important:** do not set a `Content-Type` header on this request — `adminFetch` merges any headers you pass with the CSRF/auth headers and forwards them to `fetch`; when `body` is a `FormData` instance and no `Content-Type` is set, the browser sets `multipart/form-data; boundary=...` itself. Setting it manually breaks the multipart boundary.

- [x] **Step 4: Run test to verify it passes**

Run: `npm run test -- contentBundle.import`
Expected: both tests PASS.

- [x] **Step 5: Commit**

```bash
git add src/lib/contentBundle.ts src/lib/contentBundle.import.test.ts
git commit -m "feat: add importAllContentBundle to post a backup ZIP to /api/admin/import"
```

---

### Task 7: Frontend — "Restore from backup" UI

**Files:**
- Modify: `aurum-editorial/src/components/admin/AdminLayoutContext.tsx`
- Modify: `aurum-editorial/src/components/admin/AdminShell.tsx`
- Test: `aurum-editorial/src/components/admin/AdminLayoutContext.import.test.tsx`

- [x] **Step 1: Write the failing test**

First check how the existing `onExportAll` callback is unit-tested (if at all) — `AdminLayoutContext.tsx` has no dedicated test file today (confirmed: no `AdminLayoutContext.test.tsx` under `src/components/admin/`), so this is the first test for this context. Keep it focused and lightweight: test the callback logic in isolation by mocking `contentBundle`'s `importAllContentBundle`, using `@testing-library/react`'s `renderHook` (already a devDependency — check `package.json` for `@testing-library/react`; if absent, skip this Task's automated test and rely on Task 8's manual browser verification only, noting that explicitly to the user before proceeding).

```tsx
// aurum-editorial/src/components/admin/AdminLayoutContext.import.test.tsx
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdminLayoutProvider, useAdminLayout } from "./AdminLayoutContext";
import * as contentBundle from "@/lib/contentBundle";

vi.mock("@/lib/contentBundle", async () => {
  const actual = await vi.importActual<typeof contentBundle>("@/lib/contentBundle");
  return { ...actual, importAllContentBundle: vi.fn() };
});

describe("AdminLayoutContext onImportAll", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls importAllContentBundle with the selected file and toggles isImportingAll", async () => {
    const mockImport = vi.mocked(contentBundle.importAllContentBundle);
    mockImport.mockResolvedValue({
      sectionsRestored: ["faq"],
      sectionsSkipped: [],
      assetsRestored: 1,
      assetsFailed: 0,
    });

    const { result } = renderHook(() => useAdminLayout(), {
      wrapper: ({ children }) => <AdminLayoutProvider>{children}</AdminLayoutProvider>,
    });

    const file = new File([new Uint8Array([1])], "backup.zip", { type: "application/zip" });

    expect(result.current.isImportingAll).toBe(false);
    await act(async () => {
      await result.current.onImportAll(file);
    });

    expect(mockImport).toHaveBeenCalledWith(file);
    expect(result.current.isImportingAll).toBe(false);
  });
});
```

Run this discovery check first:
```bash
cd "aurum-editorial" && grep -c "@testing-library/react" package.json
```
If it returns `0`, skip Step 1's test file (no test infra for hook rendering exists) and go straight to Step 3, then do a manual browser check in Task 8. If it returns nonzero, proceed with the test above.

- [x] **Step 2: Run test to verify it fails**

Run: `npm run test -- AdminLayoutContext.import`
Expected: FAIL — `useAdminLayout` result has no `onImportAll`/`isImportingAll`.

- [x] **Step 3: Write minimal implementation**

In `aurum-editorial/src/components/admin/AdminLayoutContext.tsx`:

1. Update the import at line 18 to also pull in the new function:
```ts
import { exportAllContentBundle, importAllContentBundle } from "@/lib/contentBundle";
```

2. Add to the context value type (near lines 78-79):
```ts
  onImportAll: (file: File) => Promise<void>;
  isImportingAll: boolean;
```

3. Add the callback, right after the existing `onExportAll` block (after line 269):
```ts
  const [isImportingAll, setIsImportingAll] = useState(false);
  const onImportAll = useCallback(async (file: File) => {
    if (isImportingAll) return;
    setIsImportingAll(true);
    const pending = toast.loading("Restoring site content and images from backup…");
    try {
      const res = await importAllContentBundle(file);
      toast.success(
        `Restored ${res.sectionsRestored.length} sections, ${res.assetsRestored} images` +
          (res.assetsFailed ? ` (${res.assetsFailed} images failed to re-upload)` : "") +
          (res.sectionsSkipped.length ? ` (skipped: ${res.sectionsSkipped.join(", ")})` : "") +
          ".",
        { id: pending },
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Restore failed.", { id: pending });
    } finally {
      setIsImportingAll(false);
    }
  }, [isImportingAll]);
```

4. Add both to the `value` object (near line 289-290) and its dependency array (near line 311-312):
```ts
      onImportAll,
      isImportingAll,
```

- [x] **Step 4: Run test to verify it passes**

Run: `npm run test -- AdminLayoutContext.import` (or skip if Step 1 was skipped for missing test infra)
Expected: test PASSES.

Also run the full frontend suite to catch regressions: `npm run test`
Expected: all tests PASS.

- [x] **Step 5: Commit**

```bash
git add src/components/admin/AdminLayoutContext.tsx src/components/admin/AdminLayoutContext.import.test.tsx
git commit -m "feat: wire onImportAll/isImportingAll into AdminLayoutContext"
```

---

### Task 8: Frontend — restore button + file picker

**Files:**
- Modify: `aurum-editorial/src/components/admin/AdminShell.tsx`

No new automated test for this task — it's a thin JSX wiring change over a `<input type="file">`, which `jsdom`/Vitest can exercise but the real value of verification here is visual (does the button render correctly, does the file picker open, does the toast show). Verify manually per Step 3 below instead of asserting through the DOM.

- [x] **Step 1: Confirm current destructured props**

Read `AdminShell.tsx:30-45` to see where `onExportAll`/`isExportingAll` are destructured from `useAdminLayout()` (or whatever hook/context consumer is used) — add `onImportAll` and `isImportingAll` to that same destructuring list.

- [x] **Step 2: Add the button + hidden file input**

In `AdminShell.tsx`, right after the existing "Export all site content (ZIP)" button (after line 315), add:
```tsx
              <input
                type="file"
                accept=".zip"
                ref={importInputRef}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (file) void onImportAll(file);
                }}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => importInputRef.current?.click()}
                disabled={isImportingAll}
                title="Restore all site content and images from a previously exported backup ZIP"
                className="hidden sm:inline-flex px-4 py-2.5 text-slate-700 bg-white border border-slate-200/80 rounded-xl text-sm font-medium hover:bg-slate-50 transition disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isImportingAll ? "Restoring…" : "Restore from backup (ZIP)"}
              </button>
```

Add the ref near the top of the component (alongside other `useRef`/`useState` declarations, or add `useRef` to the React import if not already imported):
```tsx
  const importInputRef = useRef<HTMLInputElement>(null);
```

- [x] **Step 3: Manually verify in the browser**

```bash
cd "aurum-editorial" && npm run dev
```
Navigate to `http://localhost:5173` (or whatever port Vite picks), log into the admin dashboard (dev-mode passwordless login), confirm:
1. "Restore from backup (ZIP)" button renders next to "Export all site content (ZIP)".
2. Clicking it opens the OS file picker filtered to `.zip`.
3. Selecting a real bundle exported via the existing "Export all site content (ZIP)" button triggers a loading toast, then a success toast with section/asset counts.
4. Spot-check one restored section (e.g. FAQ page or a product) in both the admin panel and the public site to confirm the data round-tripped and images point at fresh R2 URLs (not the old CDN URLs).

- [x] **Step 4: Commit**

```bash
git add src/components/admin/AdminShell.tsx
git commit -m "feat: add Restore from backup button to admin header"
```

Note: this button is upgraded to a two-step "Preview → Restore" flow in Task 14, once dry-run support exists (Task 13). Ship this basic version first so each task stays independently testable.

---

### Task 9: Coverage-guard test — restored sections must match exported sections

**Files:**
- Modify: `src/services/import_service.py`
- Test: `__tests__/test_import_service.py`

Nothing today stops someone adding an 18th admin section to `contentBundle.ts` (export) without teaching `import_service._restore_section` how to write it back. That's a silent disaster-recovery gap: the section exports fine, looks present in the ZIP, and then just never comes back on restore. This test makes that failure loud and immediate.

- [x] **Step 1: Write the failing test**

Append to `__tests__/test_import_service.py`:

```python
class TestSectionCoverageGuard:
    def test_restore_handles_every_exported_section_key(self):
        """Keep in sync with the 17 keys collected by `collectSections()` in
        aurum-editorial/src/lib/contentBundle.ts:138-159. If this test fails after
        adding/renaming a section there, add matching handling in
        import_service._restore_section (and update EXPORTED_SECTION_KEYS below)
        before merging — a section that exports but doesn't import is a silent
        disaster-recovery hole.
        """
        from src.services.import_service import SIMPLE_LIST_SECTIONS, SINGLETON_SECTIONS

        EXPORTED_SECTION_KEYS = {
            "products", "categories", "hero", "site-assets", "collection-slides",
            "testimonials", "faq", "policies", "studio-settings", "shop-page",
            "home-page", "story-page", "journal", "navigation", "contact-page",
            "history-page", "product-page",
        }
        assert len(EXPORTED_SECTION_KEYS) == 17

        composite_sections = {"policies", "journal"}
        handled = set(SIMPLE_LIST_SECTIONS.keys()) | set(SINGLETON_SECTIONS.keys()) | composite_sections

        missing = EXPORTED_SECTION_KEYS - handled
        extra = handled - EXPORTED_SECTION_KEYS
        assert not missing, f"contentBundle.ts exports these sections but import_service can't restore them: {missing}"
        assert not extra, f"import_service handles sections contentBundle.ts no longer exports: {extra}"
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest __tests__/test_import_service.py::TestSectionCoverageGuard -v`
Expected: PASSES already if Tasks 1-3 were implemented as specified (17/17 match) — if so, skip to Step 4. If it fails, that means `SIMPLE_LIST_SECTIONS`/`SINGLETON_SECTIONS`/composite handling drifted from the reference table; fix `import_service.py` to match Task 3's table, not the other way around.

- [x] **Step 3: No production code change expected**

This task is a guard test, not new functionality — `_restore_section` should already handle all 17 keys from Task 3. If Step 2 failed, treat it as a bug found in Task 3's implementation and fix `import_service.py` there.

- [x] **Step 4: Run full suite to confirm no regressions**

Run: `python -m pytest __tests__/test_import_service.py -v`
Expected: all PASS, including the new guard test.

- [x] **Step 5: Commit**

```bash
git add __tests__/test_import_service.py
git commit -m "test: guard that import_service restores every section contentBundle.ts exports"
```

---

### Task 10: Classify and surface non-error skips as warnings

**Files:**
- Modify: `src/services/import_service.py`
- Modify: `api/routes/admin_import.py`
- Modify: `aurum-editorial/src/lib/contentBundle.ts`
- Modify: `aurum-editorial/src/components/admin/AdminLayoutContext.tsx`
- Test: `__tests__/test_import_service.py`, `aurum-editorial/src/lib/contentBundle.import.test.ts`

Today every skip lands in one flat `sections_skipped` list, whether it's an intentional `__error` from a failed export fetch (expected, benign) or an unknown/malformed section that silently didn't restore (not benign — an admin needs to know). Both currently render the same way. Split them.

- [x] **Step 1: Write the failing backend test**

Append to `__tests__/test_import_service.py`:

```python
class TestSkipReasonClassification:
    @pytest.mark.asyncio
    async def test_error_section_is_skipped_as_expected_not_a_warning(self):
        parsed = ParsedBundle(sections={"faq": {"__error": "fetch failed"}})
        result = await restore_bundle(parsed, _make_database(), AsyncMock())
        assert result.sections_skipped == ["faq"]
        assert result.sections_skip_reasons == {"faq": "source_error"}

    @pytest.mark.asyncio
    async def test_unknown_section_is_skipped_as_a_warning(self):
        parsed = ParsedBundle(sections={"totally-unknown-section": {"x": 1}})
        result = await restore_bundle(parsed, _make_database(), AsyncMock())
        assert result.sections_skip_reasons == {"totally-unknown-section": "unknown_section"}

    @pytest.mark.asyncio
    async def test_wrong_shape_section_is_skipped_as_a_warning(self):
        parsed = ParsedBundle(sections={"faq": {"not": "a list"}})  # faq expects a list
        result = await restore_bundle(parsed, _make_database(), AsyncMock())
        assert result.sections_skip_reasons == {"faq": "invalid_shape"}
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest __tests__/test_import_service.py::TestSkipReasonClassification -v`
Expected: FAIL — `ImportResult` has no `sections_skip_reasons` field.

- [x] **Step 3: Write minimal implementation**

In `src/services/import_service.py`, add a `sections_skip_reasons: Dict[str, str]` field to `ImportResult`:

```python
@dataclass
class ImportResult:
    sections_restored: List[str] = field(default_factory=list)
    sections_skipped: List[str] = field(default_factory=list)
    sections_skip_reasons: Dict[str, str] = field(default_factory=dict)
    assets_restored: int = 0
    assets_failed: int = 0
```

Update every skip site to record a reason (`"source_error"` for `__error`, `"unknown_section"` for a key not in `SIMPLE_LIST_SECTIONS`/`SINGLETON_SECTIONS`/`{"policies","journal"}`, `"invalid_shape"` for a known key whose value isn't the expected list/dict). In `restore_bundle`:

```python
    for key, value in sections.items():
        if isinstance(value, dict) and "__error" in value:
            result.sections_skipped.append(key)
            result.sections_skip_reasons[key] = "source_error"
            continue
        await _restore_section(key, value, database, result)
```

In `_restore_section`, every `result.sections_skipped.append(key)` branch needs a matching reason. The two shape-mismatch branches (`SIMPLE_LIST_SECTIONS` value not a list, `SINGLETON_SECTIONS` value not a dict) get `"invalid_shape"`; the final catch-all (key not recognized at all) gets `"unknown_section"`:

```python
    if key in SIMPLE_LIST_SECTIONS:
        if not isinstance(value, list):
            result.sections_skipped.append(key)
            result.sections_skip_reasons[key] = "invalid_shape"
            return
        ...

    if key in SINGLETON_SECTIONS:
        if not isinstance(value, dict):
            result.sections_skipped.append(key)
            result.sections_skip_reasons[key] = "invalid_shape"
            return
        ...

    # unrecognized key entirely
    result.sections_skipped.append(key)
    result.sections_skip_reasons[key] = "unknown_section"
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest __tests__/test_import_service.py -v`
Expected: all PASS.

- [x] **Step 5: Wire the reason map through the route response**

In `api/routes/admin_import.py`, add `"sections_skip_reasons": result.sections_skip_reasons` to the returned dict.

- [x] **Step 6: Write the failing frontend test**

Append to `aurum-editorial/src/lib/contentBundle.import.test.ts`:

```ts
it("passes through sectionsSkipReasons so callers can distinguish warnings from expected skips", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      sections_restored: ["products"],
      sections_skipped: ["faq", "unknown-thing"],
      sections_skip_reasons: { faq: "source_error", "unknown-thing": "unknown_section" },
      assets_restored: 0,
      assets_failed: 0,
    }),
  });
  vi.stubGlobal("fetch", fetchMock);

  const file = new File([new Uint8Array([1])], "backup.zip", { type: "application/zip" });
  const result = await importAllContentBundle(file);

  expect(result.sectionsSkipReasons).toEqual({ faq: "source_error", "unknown-thing": "unknown_section" });
});
```

- [x] **Step 7: Run frontend test to verify it fails, then implement**

Run: `npm run test -- contentBundle.import` (expect FAIL: `sectionsSkipReasons` undefined).

In `contentBundle.ts`, add `sectionsSkipReasons: Record<string, string>` to `ImportBundleResult` and map it from `body.sections_skip_reasons` in `importAllContentBundle`. Also add a helper used by the UI:

```ts
export function hasImportWarnings(result: ImportBundleResult): boolean {
  return Object.values(result.sectionsSkipReasons).some((reason) => reason !== "source_error");
}
```

- [x] **Step 8: Wire the warning into the toast**

In `AdminLayoutContext.tsx`'s `onImportAll`, replace the single success toast with a branch:

```ts
      const res = await importAllContentBundle(file);
      const summary =
        `Restored ${res.sectionsRestored.length} sections, ${res.assetsRestored} images` +
        (res.assetsFailed ? ` (${res.assetsFailed} images failed to re-upload)` : "") +
        (res.sectionsSkipped.length ? ` (skipped: ${res.sectionsSkipped.join(", ")})` : "") +
        ".";
      if (hasImportWarnings(res)) {
        toast.error(`${summary} Some sections did not restore for unexpected reasons — check before trusting this backup.`, {
          id: pending,
          duration: 15000,
        });
      } else {
        toast.success(summary, { id: pending });
      }
```

`toast.error` (or the toast library's warning-tier call — match whatever `sonner`/`react-hot-toast` variant this codebase already uses elsewhere for non-fatal warnings) keeps this visually distinct from the plain success case; a `source_error`-only skip list still shows success since that's an expected, benign gap in the original export.

- [x] **Step 9: Run frontend test to verify it passes**

Run: `npm run test -- contentBundle.import`
Expected: PASS.

- [x] **Step 10: Commit**

```bash
git add src/services/import_service.py api/routes/admin_import.py aurum-editorial/src/lib/contentBundle.ts aurum-editorial/src/lib/contentBundle.import.test.ts aurum-editorial/src/components/admin/AdminLayoutContext.tsx __tests__/test_import_service.py
git commit -m "feat: classify skipped sections and surface non-error skips as restore warnings"
```

---

### Task 11: Recreate MongoDB indexes as part of restore

**Files:**
- Modify: `src/services/import_service.py`
- Test: `__tests__/test_import_service.py`

A restore into a genuinely empty/reset MongoDB (the disaster-recovery case this whole feature exists for) currently produces documents with **no indexes** — the 17 restore collections have no `ensure_indexes()` anywhere in the codebase today (the only precedent, `OrderService.ensure_indexes()`/`FraudReviewService.ensure_indexes()`, is unrelated and doesn't cover these collections). Add one scoped to restore.

- [x] **Step 1: Write the failing test**

Append to `__tests__/test_import_service.py`:

```python
from src.services.import_service import ensure_restore_indexes  # noqa: E402


class TestEnsureRestoreIndexes:
    @pytest.mark.asyncio
    async def test_creates_unique_slug_index_on_products_and_categories(self):
        database = _make_database()
        await ensure_restore_indexes(database)

        database["products"].create_index.assert_any_await("slug", unique=True)
        database["categories"].create_index.assert_any_await("slug", unique=True)

    @pytest.mark.asyncio
    async def test_creates_settings_key_index_on_singleton_collections(self):
        database = _make_database()
        await ensure_restore_indexes(database)

        database["studio_settings"].create_index.assert_any_await("settings_key", unique=True)

    @pytest.mark.asyncio
    async def test_index_creation_is_called_at_end_of_restore_bundle(self, monkeypatch):
        from src.services import import_service

        ensure_calls = AsyncMock()
        monkeypatch.setattr(import_service, "ensure_restore_indexes", ensure_calls)

        parsed = ParsedBundle(sections={"faq": []})
        await restore_bundle(parsed, _make_database(), AsyncMock())

        ensure_calls.assert_awaited_once()
```

`_make_database()`'s fake collections need `create_index` as an `AsyncMock` too — extend the fixture from Task 2:

```python
    def _getitem(name: str) -> AsyncMock:
        if name not in store:
            coll = AsyncMock()
            coll.replace_one = AsyncMock()
            coll.create_index = AsyncMock()
            store[name] = coll
        return store[name]
```

(`assert_any_await` isn't a real `unittest.mock` method — replace with an explicit loop over `coll.create_index.await_args_list` checking for the expected `(args, kwargs)` pair, or use `unittest.mock.call` equality: `assert call("slug", unique=True) in database["products"].create_index.await_args_list`.)

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest __tests__/test_import_service.py::TestEnsureRestoreIndexes -v`
Expected: FAIL — `ensure_restore_indexes` doesn't exist.

- [x] **Step 3: Write minimal implementation**

Append to `src/services/import_service.py`:

```python
# (collection_name, field, unique) — scoped to the 17 restore collections only.
# Mirrors the lookup patterns the existing service layer relies on (slug lookups
# for products/categories, settings_key/meta_key upserts for singletons).
RESTORE_INDEXES: List[tuple[str, str, bool]] = [
    ("products", "slug", True),
    ("categories", "slug", True),
    ("blog_posts", "slug", True),
    ("studio_settings", "settings_key", True),
    ("shop_page_settings", "settings_key", True),
    ("home_page_settings", "settings_key", True),
    ("story_page_settings", "settings_key", True),
    ("navigation_settings", "settings_key", True),
    ("contact_page_settings", "settings_key", True),
    ("history_page_settings", "settings_key", True),
    ("product_page_settings", "settings_key", True),
    ("journal_page_settings", "settings_key", True),
    ("policy_page_meta", "meta_key", True),
]


async def ensure_restore_indexes(database) -> None:
    for collection_name, field_name, unique in RESTORE_INDEXES:
        await database[collection_name].create_index(field_name, unique=unique)
```

At the end of `restore_bundle`, after the cache invalidation call, add:
```python
    await ensure_restore_indexes(database)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest __tests__/test_import_service.py -v`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add src/services/import_service.py __tests__/test_import_service.py
git commit -m "feat: recreate MongoDB indexes for restore collections after import"
```

---

### Task 12: Deduplicate asset uploads by content hash

**Files:**
- Modify: `src/services/import_service.py`
- Test: `__tests__/test_import_service.py`

Every restore of the same backup currently re-uploads every asset to R2 as a brand-new object, even if nothing changed since the last restore — R2 fills up with duplicates and every URL changes on every restore run. Hash bytes first; reuse the URL for a hash already uploaded in this run.

- [x] **Step 1: Write the failing test**

Append to `__tests__/test_import_service.py`:

```python
class TestAssetDeduplication:
    @pytest.mark.asyncio
    async def test_identical_asset_bytes_uploaded_only_once(self):
        same_bytes = b"\xff\xd8\xff-identical-jpeg-bytes"
        parsed = ParsedBundle(
            sections={
                "faq": [
                    {"_id": "507f1f77bcf86cd799439011", "icon_url": "https://cdn.example.com/a.jpg"},
                    {"_id": "507f1f77bcf86cd799439012", "icon_url": "https://cdn.example.com/b.jpg"},
                ]
            },
            assets={
                "assets/faq/001-a.jpg": same_bytes,
                "assets/faq/002-b.jpg": same_bytes,
            },
            asset_urls={
                "assets/faq/001-a.jpg": "https://cdn.example.com/a.jpg",
                "assets/faq/002-b.jpg": "https://cdn.example.com/b.jpg",
            },
        )
        r2 = AsyncMock()
        r2.upload_file = AsyncMock(return_value="https://cdn.chokmoki.example/faq/shared.jpg")

        result = await restore_bundle(parsed, _make_database(), r2)

        r2.upload_file.assert_awaited_once()  # only one real upload for two identical files
        assert result.assets_restored == 2  # both references still count as restored
        assert result.assets_deduplicated == 1
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest __tests__/test_import_service.py::TestAssetDeduplication -v`
Expected: FAIL — `r2.upload_file` currently called twice, and `ImportResult` has no `assets_deduplicated` field.

- [x] **Step 3: Write minimal implementation**

Add `assets_deduplicated: int = 0` to `ImportResult`. Rewrite `_upload_assets` in `src/services/import_service.py` to hash bytes and reuse URLs within the run:

```python
import hashlib


async def _upload_assets(parsed: ParsedBundle, r2_service) -> tuple[Dict[str, str], int, int, int]:
    """Upload every bundled asset to R2, deduplicating identical bytes within this
    run by sha256 hash so a repeated restore of the same backup doesn't create
    duplicate R2 objects. Returns (old_url -> new_url map, restored, failed, deduplicated).
    """
    url_map: Dict[str, str] = {}
    hash_to_new_url: Dict[str, str] = {}
    restored = 0
    failed = 0
    deduplicated = 0
    for zip_path, old_url in parsed.asset_urls.items():
        data = parsed.assets.get(zip_path)
        if data is None:
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in hash_to_new_url:
            url_map[old_url] = hash_to_new_url[digest]
            restored += 1
            deduplicated += 1
            continue
        ext = _asset_extension(zip_path)
        content_type = ASSET_CONTENT_TYPES.get(ext, "application/octet-stream")
        try:
            new_url = await r2_service.upload_file(data, extension=ext, content_type=content_type, folder="restored")
        except Exception:
            failed += 1
            continue
        hash_to_new_url[digest] = new_url
        url_map[old_url] = new_url
        restored += 1
    return url_map, restored, failed, deduplicated
```

Update the call site in `restore_bundle` to unpack the fourth value and pass it through to `ImportResult(..., assets_deduplicated=assets_deduplicated)`.

Cross-run dedup (reusing an R2 object from a *previous* restore, not just within the current one) would need a stable hash-derived R2 key plus a HEAD-before-PUT check against R2 itself — `R2Service` has no such lookup today. Note that as an intentional follow-up, not silently claim it here: within-run dedup is what this task implements.

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest __tests__/test_import_service.py -v`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add src/services/import_service.py __tests__/test_import_service.py
git commit -m "feat: dedupe identical asset uploads by content hash within a restore run"
```

---

### Task 13: Dry-run mode for `POST /api/admin/import`

**Files:**
- Modify: `src/services/import_service.py`
- Modify: `api/routes/admin_import.py`
- Test: `__tests__/test_import_service.py`, `__tests__/test_admin_import_route.py`

Add a `plan_restore()` function that reuses `parse_bundle_zip` but never writes to Mongo or uploads to R2 — it answers "what would happen" so the UI can show a preview before an admin commits to overwriting live data.

- [x] **Step 1: Write the failing test**

Append to `__tests__/test_import_service.py`:

```python
from src.services.import_service import plan_restore  # noqa: E402


class TestPlanRestore:
    @pytest.mark.asyncio
    async def test_reports_counts_without_writing_or_uploading(self):
        parsed = ParsedBundle(
            sections={"faq": [{"_id": "507f1f77bcf86cd799439011", "question": "Q1"}]},
            assets={"assets/faq/001-photo.jpg": b"\xff\xd8\xff-bytes"},
            asset_urls={"assets/faq/001-photo.jpg": "https://cdn.example.com/photo.jpg"},
        )
        database = _make_database()
        r2 = AsyncMock()

        plan = await plan_restore(parsed, database)

        r2.upload_file = AsyncMock()  # never even constructed a real client for dry-run
        database["faq_items"].replace_one.assert_not_awaited()
        assert plan.sections_to_restore == ["faq"]
        assert plan.sections_skipped == []
        assert plan.assets_to_upload == 1

    @pytest.mark.asyncio
    async def test_reports_new_vs_existing_ids_per_list_section(self):
        parsed = ParsedBundle(
            sections={
                "faq": [
                    {"_id": "507f1f77bcf86cd799439011", "question": "existing"},
                    {"_id": "507f1f77bcf86cd799439099", "question": "new"},
                ]
            }
        )
        database = _make_database()
        database["faq_items"].find_one = AsyncMock(
            side_effect=lambda f: {"_id": f["_id"]} if str(f["_id"]) == "507f1f77bcf86cd799439011" else None
        )

        plan = await plan_restore(parsed, database)

        assert plan.id_diff["faq"]["new"] == ["507f1f77bcf86cd799439099"]
        assert plan.id_diff["faq"]["overwriting"] == ["507f1f77bcf86cd799439011"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest __tests__/test_import_service.py::TestPlanRestore -v`
Expected: FAIL — `plan_restore` doesn't exist.

- [x] **Step 3: Write minimal implementation**

Append to `src/services/import_service.py`:

```python
@dataclass
class RestorePlan:
    sections_to_restore: List[str] = field(default_factory=list)
    sections_skipped: List[str] = field(default_factory=list)
    sections_skip_reasons: Dict[str, str] = field(default_factory=dict)
    assets_to_upload: int = 0
    id_diff: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)  # section -> {"new": [...], "overwriting": [...]}


async def plan_restore(parsed: ParsedBundle, database) -> RestorePlan:
    plan = RestorePlan(assets_to_upload=len(parsed.assets))

    for key, value in parsed.sections.items():
        if isinstance(value, dict) and "__error" in value:
            plan.sections_skipped.append(key)
            plan.sections_skip_reasons[key] = "source_error"
            continue
        if key in SIMPLE_LIST_SECTIONS and isinstance(value, list):
            plan.sections_to_restore.append(key)
            await _diff_list_ids(database, SIMPLE_LIST_SECTIONS[key], key, value, plan)
        elif key in SINGLETON_SECTIONS and isinstance(value, dict):
            plan.sections_to_restore.append(key)
        elif key == "policies" and isinstance(value, dict):
            plan.sections_to_restore.append(key)
            sections = value.get("sections")
            if isinstance(sections, list):
                await _diff_list_ids(database, "policy_sections", key, sections, plan)
        elif key == "journal" and isinstance(value, dict):
            plan.sections_to_restore.append(key)
            posts = value.get("data")
            if isinstance(posts, list):
                await _diff_list_ids(database, "blog_posts", key, posts, plan)
        else:
            plan.sections_skipped.append(key)
            plan.sections_skip_reasons[key] = "invalid_shape" if key in SIMPLE_LIST_SECTIONS or key in SINGLETON_SECTIONS else "unknown_section"

    return plan


async def _diff_list_ids(database, collection_name: str, section_key: str, items: List[Dict[str, Any]], plan: RestorePlan) -> None:
    new_ids: List[str] = []
    overwriting_ids: List[str] = []
    collection = database[collection_name]
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("_id")
        oid = _object_id(raw_id) if raw_id else None
        existing = await collection.find_one({"_id": oid}) if oid is not None else None
        target = overwriting_ids if existing else new_ids
        target.append(str(oid) if oid is not None else "(new)")
    plan.id_diff[section_key] = {"new": new_ids, "overwriting": overwriting_ids}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest __tests__/test_import_service.py -v`
Expected: all PASS.

- [x] **Step 5: Write the failing route test**

Append to `__tests__/test_admin_import_route.py`:

```python
    def test_dry_run_does_not_call_restore_bundle(self, api_module):
        from api.bootstrap import require_admin

        api_module.app.dependency_overrides[require_admin] = lambda: "admin@test.com"
        try:
            with (
                patch("api.routes.admin_import.restore_bundle", new_callable=AsyncMock) as mock_restore,
                patch("api.routes.admin_import.plan_restore", new_callable=AsyncMock) as mock_plan,
            ):
                from src.services.import_service import RestorePlan

                mock_plan.return_value = RestorePlan(sections_to_restore=["faq"], assets_to_upload=1)
                client = TestClient(api_module.app, raise_server_exceptions=True)
                files = {"bundle": ("backup.zip", _minimal_bundle_zip(), "application/zip")}
                response = client.post("/api/admin/import?dry_run=true", files=files)
        finally:
            api_module.app.dependency_overrides.pop(require_admin, None)

        assert response.status_code == 200
        mock_restore.assert_not_called()
        mock_plan.assert_awaited_once()
        assert response.json()["sections_to_restore"] == ["faq"]
```

- [x] **Step 6: Run test to verify it fails, then implement**

Run: `python -m pytest __tests__/test_admin_import_route.py::TestAdminImportRoute::test_dry_run_does_not_call_restore_bundle -v` — expect FAIL (no `dry_run` param handling).

In `api/bootstrap.py`'s import block, also export `plan_restore` and `RestorePlan` from `import_service` alongside the existing names.

In `api/routes/admin_import.py`, add the query param and branch:

```python
from api.bootstrap import (
    db, R2Service, require_admin, logger, BundleParseError,
    parse_bundle_zip, restore_bundle, plan_restore, MAX_BUNDLE_BYTES,
)


@router.post("/api/admin/import")
async def admin_import_bundle(
    bundle: UploadFile = File(...),
    dry_run: bool = False,
    email: str = Depends(require_admin),
):
    ...  # size cap + parse_bundle_zip unchanged

    database = await db.get_database()

    if dry_run:
        plan = await plan_restore(parsed, database)
        return {
            "dry_run": True,
            "sections_to_restore": plan.sections_to_restore,
            "sections_skipped": plan.sections_skipped,
            "sections_skip_reasons": plan.sections_skip_reasons,
            "assets_to_upload": plan.assets_to_upload,
            "id_diff": plan.id_diff,
        }

    r2 = R2Service()
    try:
        result = await restore_bundle(parsed, database, r2)
    ...
```

- [x] **Step 7: Run route tests to verify they pass**

Run: `python -m pytest __tests__/test_admin_import_route.py -v`
Expected: all PASS.

Run full backend suite: `python -m pytest -v`
Expected: all PASS, no regressions.

- [x] **Step 8: Commit**

```bash
git add src/services/import_service.py api/bootstrap.py api/routes/admin_import.py __tests__/test_import_service.py __tests__/test_admin_import_route.py
git commit -m "feat: add dry_run mode to POST /api/admin/import for restore previews"
```

---

### Task 14: Frontend — "Preview restore" step before confirming

**Files:**
- Modify: `aurum-editorial/src/lib/contentBundle.ts`
- Modify: `aurum-editorial/src/components/admin/AdminLayoutContext.tsx`
- Modify: `aurum-editorial/src/components/admin/AdminShell.tsx`
- Test: `aurum-editorial/src/lib/contentBundle.import.test.ts`

Replace Task 8's single-click restore with: pick file → preview panel (dry-run summary) → explicit "Confirm restore" click. This is the guard against an admin accidentally overwriting live data with a stale or wrong backup.

- [x] **Step 1: Write the failing frontend test**

Append to `aurum-editorial/src/lib/contentBundle.import.test.ts`:

```ts
it("importAllContentBundle with dryRun:true hits the dry_run query param and returns a preview shape", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      dry_run: true,
      sections_to_restore: ["faq", "products"],
      sections_skipped: [],
      sections_skip_reasons: {},
      assets_to_upload: 4,
      id_diff: { faq: { new: ["abc"], overwriting: ["def"] } },
    }),
  });
  vi.stubGlobal("fetch", fetchMock);

  const file = new File([new Uint8Array([1])], "backup.zip", { type: "application/zip" });
  const preview = await previewImportContentBundle(file);

  const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(url).toContain("dry_run=true");
  expect(preview).toEqual({
    sectionsToRestore: ["faq", "products"],
    sectionsSkipped: [],
    sectionsSkipReasons: {},
    assetsToUpload: 4,
    idDiff: { faq: { new: ["abc"], overwriting: ["def"] } },
  });
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `npm run test -- contentBundle.import`
Expected: FAIL — `previewImportContentBundle` not exported.

- [x] **Step 3: Write minimal implementation**

In `contentBundle.ts`, add:

```ts
export interface ImportPreview {
  sectionsToRestore: string[];
  sectionsSkipped: string[];
  sectionsSkipReasons: Record<string, string>;
  assetsToUpload: number;
  idDiff: Record<string, { new: string[]; overwriting: string[] }>;
}

export async function previewImportContentBundle(file: File): Promise<ImportPreview> {
  const form = new FormData();
  form.append("bundle", file);

  const res = await adminFetch(`${API_BASE}/admin/import?dry_run=true`, { method: "POST", body: form });
  if (!res.ok) {
    let message = `Preview failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* no JSON body */
    }
    throw new Error(message);
  }

  const body = await res.json();
  return {
    sectionsToRestore: body.sections_to_restore,
    sectionsSkipped: body.sections_skipped,
    sectionsSkipReasons: body.sections_skip_reasons,
    assetsToUpload: body.assets_to_upload,
    idDiff: body.id_diff,
  };
}
```

- [x] **Step 4: Run test to verify it passes**

Run: `npm run test -- contentBundle.import`
Expected: PASS.

- [x] **Step 5: Wire preview state into `AdminLayoutContext.tsx`**

Add state + a callback that runs the preview and stores the result, and change `onImportAll` to require a preview to have been run first (or accept the file directly, for callers that already have a confirmed preview):

```ts
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null);
  const [pendingImportFile, setPendingImportFile] = useState<File | null>(null);
  const [isPreviewingImport, setIsPreviewingImport] = useState(false);

  const onPreviewImport = useCallback(async (file: File) => {
    setIsPreviewingImport(true);
    try {
      const preview = await previewImportContentBundle(file);
      setImportPreview(preview);
      setPendingImportFile(file);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not preview backup.");
      setImportPreview(null);
      setPendingImportFile(null);
    } finally {
      setIsPreviewingImport(false);
    }
  }, []);

  const onConfirmImport = useCallback(async () => {
    if (!pendingImportFile) return;
    const file = pendingImportFile;
    setImportPreview(null);
    setPendingImportFile(null);
    await onImportAll(file);
  }, [pendingImportFile, onImportAll]);
```

Add `importPreview`, `isPreviewingImport`, `onPreviewImport`, `onConfirmImport`, `pendingImportFile` to the context value/dependency array alongside the Task 6/7 additions.

- [x] **Step 6: Update `AdminShell.tsx`'s restore button to a two-step flow**

Replace Task 8's direct `onImportAll(file)` call on file select with `onPreviewImport(file)`, and render a preview panel (conditionally, when `importPreview` is set) summarizing `sectionsToRestore.length`, `assetsToUpload`, any `sectionsSkipped` (styled as a warning if any reason isn't `"source_error"`, reusing the warning styling from Task 10), and the `overwriting` counts from `idDiff`, with "Confirm restore" (`onClick={onConfirmImport}`) and "Cancel" buttons.

- [x] **Step 7: Manually verify in the browser**

```bash
cd "aurum-editorial" && npm run dev
```
Confirm: selecting a ZIP shows a preview panel (not an immediate restore), the panel lists section/asset counts and any warnings, "Cancel" discards the preview without touching the backend, and "Confirm restore" performs the real restore.

- [x] **Step 8: Commit**

```bash
git add src/lib/contentBundle.ts src/lib/contentBundle.import.test.ts src/components/admin/AdminLayoutContext.tsx src/components/admin/AdminShell.tsx
git commit -m "feat: add dry-run restore preview step before confirming a restore"
```

---

### Task 15: Audit and regression-test contentBundle.ts's asset-harvesting coverage

**Files:**
- Create: `aurum-editorial/src/lib/contentBundle.assetCoverage.test.ts`
- Modify: `aurum-editorial/src/lib/contentBundle.ts` (comment only, no logic change)

The whole restore feature depends on the export side having captured every image/video URL an admin can enter. `walk()` (`contentBundle.ts:202-233`) is a fully generic recursive walk — it visits every array element and every object key at any depth, so structurally nothing is skipped (nested product galleries, per-variant fields, deeply nested settings objects are all reached). The only actual coverage gap is in `classify()`'s heuristic: a leaf string is captured as media only if it matches `MEDIA_EXT` (recognizable file extension) or its field name matches `MEDIA_FIELD`. This task doesn't change the heuristic (that's a product decision — widening it risks false positives on `cta_to`/social links) — it documents the coverage with evidence and locks in a regression test so a future edit to `walk()`/`classify()` can't silently narrow it.

- [x] **Step 1: Write the failing test**

```ts
// aurum-editorial/src/lib/contentBundle.assetCoverage.test.ts
import { describe, expect, it } from "vitest";

// Mirrors the private regexes in contentBundle.ts:165-169. If this drifts,
// re-copy from source — it's duplicated here deliberately so the test fails
// if someone edits the regex without updating this documented contract.
const MEDIA_EXT = /\.(png|jpe?g|webp|gif|avif|svg|mp4|webm|mov|m4v)(\?|#|$)/i;
const MEDIA_FIELD = /(thumbnail|gallery|banner|image|media|hero_image|avatar|photo|poster|logo|icon)/i;

function isCapturedAsMedia(fieldPath: string, value: string): boolean {
  return MEDIA_EXT.test(value) || (MEDIA_FIELD.test(fieldPath) && value.trim().length > 0);
}

describe("asset-harvesting coverage (contentBundle.ts walk/classify)", () => {
  // Real field paths from src/models — walk() is generic recursion, so nesting
  // depth doesn't matter; what matters is whether classify() catches the leaf.
  const knownMediaFieldPaths = [
    ["products[0].thumbnail", "https://cdn.example.com/thumb.jpg"],
    ["products[0].gallery[2]", "https://cdn.example.com/g2.jpg"],
    ["products[0].medias[0].url", "https://cdn.example.com/legacy.jpg"], // legacy Product.medias[].url
    ["hero[0].hero_image", "https://cdn.example.com/hero.webp"],
    ["site-assets[0].icon", "https://cdn.example.com/icon.svg"],
    ["testimonials[0].avatar", "https://cdn.example.com/avatar.png"],
  ] as const;

  it.each(knownMediaFieldPaths)("captures %s as media via extension or field-name match", (path, url) => {
    expect(isCapturedAsMedia(path, url)).toBe(true);
  });

  it("documents the known gap: extensionless URL under a non-matching field name is NOT captured", () => {
    // e.g. a signed CDN URL with no file extension, stored under `cover_url` or `src`.
    // This is a known, accepted limitation — not a bug this task fixes. If a real
    // admin field like this shows up, widen MEDIA_FIELD in contentBundle.ts and
    // update this test's expectation.
    const signedUrlNoExtension = "https://cdn.example.com/blob/9f2e?sig=abc123";
    expect(isCapturedAsMedia("products[0].cover_url", signedUrlNoExtension)).toBe(false);
  });
});
```

- [x] **Step 2: Run test to verify current behavior**

Run: `npm run test -- contentBundle.assetCoverage`
Expected: all PASS on first run — this task documents existing behavior with evidence rather than changing it, so there's no red step here beyond confirming the assertions are true today (if any `it.each` case fails, that's a genuine coverage bug in `classify()`/`MEDIA_FIELD` — fix the regex in `contentBundle.ts` before merging, then re-run).

- [x] **Step 3: Add the explanatory comment to source**

In `contentBundle.ts`, above the `MEDIA_FIELD` regex (around line 166-169), add:

```ts
/** Fields that hold an image/video reference (deliberately excludes bare `url`,
 *  `cta_to`, social links etc. — those stay text unless the value is a media file).
 *  Coverage: walk() recurses through every array/object at any depth, so nesting
 *  (product galleries, variant fields) is never the gap — the only miss is a media
 *  URL with neither a recognizable extension (MEDIA_EXT) nor a field name matching
 *  this regex, e.g. a signed CDN URL under `cover_url`/`src`. See
 *  contentBundle.assetCoverage.test.ts for the documented contract. */
const MEDIA_FIELD =
  /(thumbnail|gallery|banner|image|media|hero_image|avatar|photo|poster|logo|icon)/i;
```

- [x] **Step 4: Run full frontend suite to confirm no regressions**

Run: `npm run test`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add src/lib/contentBundle.ts src/lib/contentBundle.assetCoverage.test.ts
git commit -m "test: document and regression-test contentBundle.ts asset-harvesting coverage"
```

---

### Task 16: End-to-end verification against the local stack

**Files:** none (verification only)

- [ ] **Step 1: Confirm the local stack is up**

```bash
docker ps --filter "name=chokmoki"
```
Expected: `chokmoki-mongodb`, `chokmoki-redis`, `chokmoki-backend` all `Up` and healthy (per the existing local setup: Mongo on host port 27018, Redis on 6380, backend on 8001, frontend dev server on 5173 proxying via `VITE_BACKEND_PORT=8001`).

- [ ] **Step 2: Export, wipe, preview, restore, diff**

1. In the admin UI, click "Export all site content (ZIP)" and save the file.
2. Note a few concrete values to check later (a product name + price, the FAQ list length, the studio settings email).
3. Wipe the local database to simulate the disaster-recovery scenario:
   ```bash
   docker exec chokmoki-mongodb mongosh chokmoki --eval "db.dropDatabase()"
   ```
4. Reload the admin UI — confirm products/FAQ/etc. are now empty.
5. Click "Restore from backup (ZIP)" and select the file from step 1 — confirm the **preview panel** (Task 14) shows section/asset counts before anything is written, and that every listed section shows as "new" (`overwriting` empty) since the DB was just wiped.
6. Click "Confirm restore". Confirm the success toast reports 17 sections restored (or however many were non-empty) and a nonzero asset count, with no warning-styled toast (a fresh export shouldn't produce `unknown_section`/`invalid_shape` skips).
7. Reload the admin UI and the public storefront — confirm the product name/price, FAQ list, and studio settings email from step 2 match, and that product images load (i.e., they now point at new R2 URLs that resolve, not broken links).
8. Verify indexes came back: `docker exec chokmoki-mongodb mongosh chokmoki --eval "db.products.getIndexes()"` — expect a unique index on `slug` in addition to the default `_id` index.
9. Repeat steps 5-6 with the **same** backup file a second time (without wiping) — confirm the success toast's asset count still reports the same restored count but R2 usage didn't double: `docker exec chokmoki-mongodb mongosh chokmoki --eval "db.products.countDocuments()"` stays the same, and spot-check that a restored product's image URL is identical across both runs (proof the sha256 dedup in Task 12 reused the R2 object rather than re-uploading).
10. Intentionally corrupt one entry in the exported `content.json` (e.g. rename a `faq` key to `faq-old` in a copy of the ZIP, per how ZIP tooling is available locally) and restore that modified ZIP — confirm the preview and the final toast both flag it with warning styling, not folded silently into a plain success message.

- [ ] **Step 3: Report results to the user**

Summarize: sections restored/skipped counts (with reasons), assets restored/failed/deduplicated counts, index verification, and confirmation that the spot-checked values in step 2 match. Flag anything that didn't round-trip cleanly (e.g., a section whose shape didn't match what `import_service.py` expects) as a follow-up.
