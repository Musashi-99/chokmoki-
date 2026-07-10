"""Tests for src.services.order_backup_service — orders/order_logs backup export + restore."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.services.order_backup_service import (  # noqa: E402
    OrdersBackupParseError,
    ParsedOrdersBackup,
    export_orders_backup,
    parse_orders_backup,
    plan_orders_restore,
    restore_orders_backup,
)


class _AsyncCursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for doc in self._docs:
            yield doc


def _make_database(orders=None, order_logs=None) -> MagicMock:
    store = {
        "orders": MagicMock(),
        "order_logs": MagicMock(),
    }
    store["orders"].find = MagicMock(return_value=_AsyncCursor(orders or []))
    store["order_logs"].find = MagicMock(return_value=_AsyncCursor(order_logs or []))
    store["orders"].replace_one = AsyncMock()
    store["order_logs"].replace_one = AsyncMock()

    database = MagicMock()
    database.__getitem__.side_effect = lambda name: store[name]
    return database


class TestExportOrdersBackup:
    @pytest.mark.asyncio
    async def test_exports_orders_and_logs_as_json_safe_dict(self):
        database = _make_database(
            orders=[{"order_id": "ORD-1", "total_amount": 500, "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc)}],
            order_logs=[{"order_id": "ORD-1", "message": "created"}],
        )

        payload = await export_orders_backup(database)

        assert payload["orders"][0]["order_id"] == "ORD-1"
        assert isinstance(payload["orders"][0]["created_at"], str)
        assert payload["order_logs"][0]["order_id"] == "ORD-1"
        # Round-trips through json.dumps without error (proves JSON-safe).
        json.dumps(payload)


class TestParseOrdersBackup:
    def test_parses_valid_backup(self):
        raw = json.dumps({"orders": [{"order_id": "ORD-1"}], "order_logs": []}).encode("utf-8")
        parsed = parse_orders_backup(raw)
        assert parsed.orders == [{"order_id": "ORD-1"}]
        assert parsed.order_logs == []

    def test_inflates_iso_datetime_strings(self):
        raw = json.dumps(
            {"orders": [{"order_id": "ORD-1", "created_at": "2026-01-01T00:00:00Z"}], "order_logs": []}
        ).encode("utf-8")
        parsed = parse_orders_backup(raw)
        assert isinstance(parsed.orders[0]["created_at"], datetime)

    def test_raises_on_invalid_json(self):
        with pytest.raises(OrdersBackupParseError, match="not valid JSON"):
            parse_orders_backup(b"not json")

    def test_raises_when_orders_key_missing(self):
        raw = json.dumps({"order_logs": []}).encode("utf-8")
        with pytest.raises(OrdersBackupParseError, match="'orders'"):
            parse_orders_backup(raw)


class TestPlanOrdersRestore:
    def test_counts_orders_and_logs(self):
        parsed = ParsedOrdersBackup(orders=[{"order_id": "ORD-1"}], order_logs=[{"order_id": "ORD-1"}, {"order_id": "ORD-2"}])
        plan = plan_orders_restore(parsed)
        assert plan.orders_to_restore == 1
        assert plan.order_logs_to_restore == 2


class TestRestoreOrdersBackup:
    @pytest.mark.asyncio
    async def test_upserts_by_order_id_and_strips_id(self):
        parsed = ParsedOrdersBackup(
            orders=[{"_id": "abc123", "order_id": "ORD-1", "total_amount": 500}],
            order_logs=[{"_id": "xyz789", "order_id": "ORD-1", "message": "created"}],
        )
        database = _make_database()

        result = await restore_orders_backup(parsed, database)

        orders_filter, orders_doc = database["orders"].replace_one.await_args.args[:2]
        assert orders_filter == {"order_id": "ORD-1"}
        assert "_id" not in orders_doc
        assert database["orders"].replace_one.await_args.kwargs["upsert"] is True

        logs_filter, logs_doc = database["order_logs"].replace_one.await_args.args[:2]
        assert logs_filter == {"order_id": "ORD-1"}
        assert "_id" not in logs_doc

        assert result.orders_restored == 1
        assert result.order_logs_restored == 1
        assert result.orders_skipped == 0

    @pytest.mark.asyncio
    async def test_skips_orders_without_order_id(self):
        parsed = ParsedOrdersBackup(orders=[{"total_amount": 500}], order_logs=[])
        database = _make_database()

        result = await restore_orders_backup(parsed, database)

        database["orders"].replace_one.assert_not_awaited()
        assert result.orders_restored == 0
        assert result.orders_skipped == 1
