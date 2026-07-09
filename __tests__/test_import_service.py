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
