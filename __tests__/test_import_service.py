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
