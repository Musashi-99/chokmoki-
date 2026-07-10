"""Tests for src.services.import_service — bundle ZIP parsing and Mongo/R2 restore."""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import zipfile
from unittest.mock import AsyncMock, MagicMock, call

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.services.import_service import BundleParseError, parse_bundle_zip  # noqa: E402


def _build_zip(
    sections: dict,
    assets: dict[str, bytes] | None = None,
    manifest_rows: list[dict] | None = None,
    section_key: str | None = None,
) -> bytes:
    """Build a ZIP in the new entity-based format.

    *sections* is a flat dict (section_key -> value). Products are stored
    under a single ``products`` key (their individual content.json files
    are combined into one array).

    If *section_key* is given, the sections dict's single key is written
    as a per-entity content.json at ``sections/{section_key}/content.json``.
    Otherwise the full sections dict is split into ``sections/*/content.json``
    (one per non-product key) plus ``products/*/content.json`` for products.
    """
    if assets is None:
        assets = {}
    if manifest_rows is None:
        manifest_rows = []

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        # Write per-entity content.json files.
        if section_key:
            # Single entity
            key = section_key
            value = sections[key]
            payload = {"exported_at": "2026-07-09T00:00:00Z", "generator": "test", key: value}
            if key == "products":
                # Build individual product files
                for i, product in enumerate(value if isinstance(value, list) else [value]):
                    slug = product.get("slug") if isinstance(product, dict) else f"product-{i}"
                    zf.writestr(
                        f"products/{slug}/content.json",
                        json.dumps({"exported_at": "2026-07-09T00:00:00Z", "generator": "test", "products": product}),
                    )
            else:
                zf.writestr(f"sections/{key}/content.json", json.dumps(payload))
        else:
            # Multiple entities: build per-key content.json files
            for key, value in sections.items():
                payload = {"exported_at": "2026-07-09T00:00:00Z", "generator": "test", key: value}
                if key == "products":
                    product_list = value if isinstance(value, list) else []
                    for i, product in enumerate(product_list):
                        slug = product.get("slug") if isinstance(product, dict) else f"product-{i}"
                        zf.writestr(
                            f"products/{slug}/content.json",
                            json.dumps({
                                "exported_at": "2026-07-09T00:00:00Z",
                                "generator": "test",
                                "products": product,
                            }),
                        )
                else:
                    zf.writestr(f"sections/{key}/content.json", json.dumps(payload))

        # Write assets
        for path, data in assets.items():
            zf.writestr(path, data)

        # Write manifest.csv (new format columns)
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["Path in ZIP", "Entity", "Field", "Original Source URL", "Status", "Bytes"])
        for row in manifest_rows:
            writer.writerow([
                row.get("path", row.get("file", "")),
                row.get("entity", row.get("section", "")),
                row.get("field", ""),
                row.get("url", ""),
                row.get("status", ""),
                row.get("bytes", 0),
            ])
        zf.writestr("manifest.csv", csv_buf.getvalue())
    return buf.getvalue()


class TestParseBundleZip:
    def test_extracts_sections_from_content_json(self):
        raw = _build_zip(
            sections={"faq": [{"_id": "507f1f77bcf86cd799439011", "question": "Q1"}]},
            manifest_rows=[{
                "path": "sections/faq/content.json",
                "entity": "faq", "field": "", "url": "",
                "status": "ok", "bytes": 50,
            }],
        )
        parsed = parse_bundle_zip(raw)
        assert parsed.sections == {"faq": [{"_id": "507f1f77bcf86cd799439011", "question": "Q1"}]}

    def test_extracts_downloaded_assets_and_source_urls(self):
        raw = _build_zip(
            sections={"faq": []},
            assets={"sections/faq/images/icon_url.jpg": b"\xff\xd8\xff-fake-jpeg-bytes"},
            manifest_rows=[
                {
                    "path": "sections/faq/images/icon_url.jpg",
                    "entity": "faq",
                    "field": "icon_url",
                    "url": "https://cdn.amplifycheckout.com/faq/photo.jpg",
                    "status": "downloaded",
                    "bytes": 21,
                }
            ],
        )
        parsed = parse_bundle_zip(raw)
        assert parsed.assets["sections/faq/images/icon_url.jpg"] == b"\xff\xd8\xff-fake-jpeg-bytes"
        assert parsed.asset_urls["sections/faq/images/icon_url.jpg"] == "https://cdn.amplifycheckout.com/faq/photo.jpg"

    def test_skips_failed_manifest_rows(self):
        raw = _build_zip(
            sections={"faq": []},
            assets={},
            manifest_rows=[
                {
                    "path": "sections/faq/images/missing.jpg",
                    "entity": "faq",
                    "field": "icon_url",
                    "url": "https://cdn.amplifycheckout.com/faq/missing.jpg",
                    "status": "failed: 404",
                    "bytes": 0,
                }
            ],
        )
        parsed = parse_bundle_zip(raw)
        assert "sections/faq/images/missing.jpg" not in parsed.asset_urls

    def test_raises_bundle_parse_error_without_manifest(self):
        raw = _build_zip(sections={"faq": []})
        # Remove manifest.csv to simulate missing manifest
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw), "r") as zin:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zout:
                for item in zin.infolist():
                    if item.filename != "manifest.csv":
                        zout.writestr(item.filename, zin.read(item.filename))
        with pytest.raises(BundleParseError, match="manifest.csv"):
            parse_bundle_zip(buf.getvalue())

    def test_raises_bundle_parse_error_on_invalid_zip(self):
        with pytest.raises(BundleParseError, match="not a valid ZIP"):
            parse_bundle_zip(b"not a zip file at all")


from src.services.import_service import restore_bundle, ParsedBundle  # noqa: E402


def _make_database(collections: dict[str, AsyncMock] | None = None) -> MagicMock:
    """Fake Motor database: db["name"] returns an AsyncMock collection."""
    store: dict[str, AsyncMock] = collections or {}

    def _getitem(name: str) -> AsyncMock:
        if name not in store:
            coll = AsyncMock()
            coll.replace_one = AsyncMock()
            coll.create_index = AsyncMock()
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


class TestRestoreBundleCacheInvalidation:
    @pytest.mark.asyncio
    async def test_invalidates_cache_after_restore(self, monkeypatch):
        from src.services import import_service

        delete_pattern = AsyncMock()
        monkeypatch.setattr(import_service.cache, "delete_pattern", delete_pattern)

        parsed = ParsedBundle(sections={"faq": [{"_id": "507f1f77bcf86cd799439011", "question": "Q1"}]})
        await restore_bundle(parsed, _make_database(), AsyncMock())

        delete_pattern.assert_awaited_once_with("chokmoki:*")


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


class TestEnsureRestoreIndexes:
    @pytest.mark.asyncio
    async def test_creates_unique_slug_index_on_products_and_categories(self):
        from src.services.import_service import ensure_restore_indexes

        database = _make_database()
        await ensure_restore_indexes(database)

        assert call("slug", unique=True) in database["products"].create_index.await_args_list
        assert call("slug", unique=True) in database["categories"].create_index.await_args_list

    @pytest.mark.asyncio
    async def test_creates_settings_key_index_on_singleton_collections(self):
        from src.services.import_service import ensure_restore_indexes

        database = _make_database()
        await ensure_restore_indexes(database)

        assert call("settings_key", unique=True) in database["studio_settings"].create_index.await_args_list

    @pytest.mark.asyncio
    async def test_index_creation_is_called_at_end_of_restore_bundle(self, monkeypatch):
        from src.services import import_service

        ensure_calls = AsyncMock()
        monkeypatch.setattr(import_service, "ensure_restore_indexes", ensure_calls)

        parsed = ParsedBundle(sections={"faq": []})
        await restore_bundle(parsed, _make_database(), AsyncMock())

        ensure_calls.assert_awaited_once()


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


class TestPlanRestore:
    @pytest.mark.asyncio
    async def test_reports_counts_without_writing_or_uploading(self):
        from src.services.import_service import plan_restore

        parsed = ParsedBundle(
            sections={"faq": [{"_id": "507f1f77bcf86cd799439011", "question": "Q1"}]},
            assets={"assets/faq/001-photo.jpg": b"\xff\xd8\xff-bytes"},
            asset_urls={"assets/faq/001-photo.jpg": "https://cdn.example.com/photo.jpg"},
        )
        database = _make_database()

        plan = await plan_restore(parsed, database)

        database["faq_items"].replace_one.assert_not_awaited()
        assert plan.sections_to_restore == ["faq"]
        assert plan.sections_skipped == []
        assert plan.assets_to_upload == 1

    @pytest.mark.asyncio
    async def test_reports_new_vs_existing_ids_per_list_section(self):
        from src.services.import_service import plan_restore

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


class TestParseBundleZipOrders:
    """orders/orders.json + orders/order_logs.json live in the same ZIP as
    products/ and sections/ — one export, one manifest, one restore path."""

    def _zip_with_orders(self, orders=None, order_logs=None, include_orders_files=True):
        raw = _build_zip(
            sections={"faq": []},
            manifest_rows=[{"path": "sections/faq/content.json", "entity": "faq", "status": "ok", "bytes": 10}],
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw), "r") as zin:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zout:
                for item in zin.infolist():
                    zout.writestr(item.filename, zin.read(item.filename))
                if include_orders_files:
                    zout.writestr("orders/orders.json", json.dumps(orders if orders is not None else []))
                    zout.writestr("orders/order_logs.json", json.dumps(order_logs if order_logs is not None else []))
        return buf.getvalue()

    def test_extracts_orders_and_order_logs(self):
        raw = self._zip_with_orders(
            orders=[{"order_id": "ORD-1", "status": "paid", "created_at": "2026-07-01T00:00:00Z"}],
            order_logs=[{"order_id": "ORD-1", "event": "created"}],
        )
        parsed = parse_bundle_zip(raw)
        assert len(parsed.orders) == 1
        assert parsed.orders[0]["order_id"] == "ORD-1"
        assert len(parsed.order_logs) == 1
        assert parsed.order_logs[0]["order_id"] == "ORD-1"

    def test_inflates_iso_datetimes_in_orders(self):
        import datetime

        raw = self._zip_with_orders(orders=[{"order_id": "ORD-1", "created_at": "2026-07-01T12:30:00Z"}])
        parsed = parse_bundle_zip(raw)
        assert isinstance(parsed.orders[0]["created_at"], datetime.datetime)

    def test_missing_orders_files_yields_empty_lists(self):
        raw = self._zip_with_orders(include_orders_files=False)
        parsed = parse_bundle_zip(raw)
        assert parsed.orders == []
        assert parsed.order_logs == []

    def test_raises_on_malformed_orders_json(self):
        raw = _build_zip(
            sections={"faq": []},
            manifest_rows=[{"path": "sections/faq/content.json", "entity": "faq", "status": "ok", "bytes": 10}],
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw), "r") as zin:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zout:
                for item in zin.infolist():
                    zout.writestr(item.filename, zin.read(item.filename))
                zout.writestr("orders/orders.json", "not json")
        with pytest.raises(BundleParseError, match="orders/orders.json"):
            parse_bundle_zip(buf.getvalue())

    def test_raises_when_orders_json_is_not_a_list(self):
        raw = _build_zip(
            sections={"faq": []},
            manifest_rows=[{"path": "sections/faq/content.json", "entity": "faq", "status": "ok", "bytes": 10}],
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw), "r") as zin:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zout:
                for item in zin.infolist():
                    zout.writestr(item.filename, zin.read(item.filename))
                zout.writestr("orders/orders.json", json.dumps({"not": "a list"}))
        with pytest.raises(BundleParseError, match="must be a JSON array"):
            parse_bundle_zip(buf.getvalue())


class TestRestoreBundleOrders:
    @pytest.mark.asyncio
    async def test_restores_orders_and_order_logs_by_order_id_upsert(self):
        parsed = ParsedBundle(
            sections={},
            orders=[{"order_id": "ORD-1", "status": "paid"}],
            order_logs=[{"order_id": "ORD-1", "event": "created"}],
        )
        database = _make_database()

        result = await restore_bundle(parsed, database, AsyncMock())

        orders_coll = database["orders"]
        orders_coll.replace_one.assert_awaited_once()
        filter_arg = orders_coll.replace_one.await_args.args[0]
        assert filter_arg == {"order_id": "ORD-1"}
        assert orders_coll.replace_one.await_args.kwargs["upsert"] is True

        logs_coll = database["order_logs"]
        logs_coll.replace_one.assert_awaited_once()
        assert result.orders_restored == 1
        assert result.order_logs_restored == 1

    @pytest.mark.asyncio
    async def test_orders_without_order_id_are_skipped(self):
        parsed = ParsedBundle(sections={}, orders=[{"status": "paid"}], order_logs=[])
        database = _make_database()

        result = await restore_bundle(parsed, database, AsyncMock())

        assert result.orders_restored == 0
        assert result.orders_skipped == 1

    @pytest.mark.asyncio
    async def test_empty_orders_does_not_touch_orders_collections(self):
        parsed = ParsedBundle(sections={"faq": []})
        database = _make_database()

        result = await restore_bundle(parsed, database, AsyncMock())

        assert "orders" not in database._store
        assert "order_logs" not in database._store
        assert result.orders_restored == 0
        assert result.order_logs_restored == 0


class TestPlanRestoreOrders:
    @pytest.mark.asyncio
    async def test_reports_orders_to_restore_counts(self):
        from src.services.import_service import plan_restore

        parsed = ParsedBundle(
            sections={},
            orders=[{"order_id": "ORD-1"}, {"order_id": "ORD-2"}],
            order_logs=[{"order_id": "ORD-1", "event": "created"}],
        )
        database = _make_database()

        plan = await plan_restore(parsed, database)

        assert plan.orders_to_restore == 2
        assert plan.order_logs_to_restore == 1
