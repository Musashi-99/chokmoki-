"""Phase A — NoSQL injection, BOLA/IDOR, CQRS authorization regression tests."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError

from src.cqrs.param_models import (
    OrderListParams,
    ShippingAddressGetParams,
    ShippingAddressListParams,
)
from src.cqrs.router import CQRSRouter
from src.security.exceptions import AuthorizationError
from src.security.mongo_safe import coerce_safe_string, reject_mongo_operator_value
from src.services.order_service import OrderService


class TestMongoSafeValidation:
    def test_rejects_dict_operator(self):
        with pytest.raises(ValueError, match="must be a scalar"):
            reject_mongo_operator_value({"$ne": None}, "user_email")

    def test_rejects_list_operator(self):
        with pytest.raises(ValueError, match="must be a scalar"):
            reject_mongo_operator_value(["$gt"], "email")

    def test_coerce_safe_string_rejects_dict(self):
        with pytest.raises(ValueError, match="scalar value"):
            coerce_safe_string({"$gt": ""}, "email")


class TestCQRSParamModels:
    def test_order_list_rejects_operator_user_email(self):
        with pytest.raises(ValidationError):
            OrderListParams.model_validate(
                {"userEmail": {"$ne": None}, "limit": 1000}
            )

    def test_order_list_accepts_valid_email(self):
        params = OrderListParams.model_validate(
            {"userEmail": "customer@example.com", "limit": 20}
        )
        assert params.user_email == "customer@example.com"

    def test_shipping_address_list_rejects_operator_email(self):
        with pytest.raises(ValidationError):
            ShippingAddressListParams.model_validate({"email": {"$gt": ""}})

    def test_shipping_address_get_requires_email(self):
        with pytest.raises(ValidationError):
            ShippingAddressGetParams.model_validate({"id": "507f1f77bcf86cd799439011"})


class TestNoSQLInjectionRegression:
    @pytest.mark.asyncio
    async def test_order_list_operator_injection_blocked(self):
        with pytest.raises(ValueError):
            await CQRSRouter.execute_query(
                "order.list",
                {"userEmail": {"$ne": None}, "limit": 1000},
            )

    @pytest.mark.asyncio
    async def test_order_list_without_email_requires_admin(self):
        with pytest.raises(AuthorizationError):
            await CQRSRouter.execute_query("order.list", {"limit": 20})

    @pytest.mark.asyncio
    async def test_shipping_address_list_operator_injection_blocked(self):
        with pytest.raises(ValueError):
            await CQRSRouter.execute_query(
                "shippingAddress.list",
                {"email": {"$gt": ""}},
            )

    @pytest.mark.asyncio
    async def test_order_list_admin_can_list_all(self):
        with patch.object(
            CQRSRouter, "_is_admin", new_callable=AsyncMock, return_value=True
        ), patch.object(
            CQRSRouter.QUERIES["order.list"], "execute", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = {"data": [], "count": 0}
            result = await CQRSRouter.execute_query(
                "order.list",
                {"limit": 10},
                admin_key="valid-admin-jwt",
            )
            assert result["count"] == 0


class TestBOLARegression:
    @pytest.mark.asyncio
    async def test_shipping_address_get_without_email_blocked(self):
        with pytest.raises(ValueError):
            await CQRSRouter.execute_query(
                "shippingAddress.get",
                {"id": "507f1f77bcf86cd799439011"},
            )

    @pytest.mark.asyncio
    async def test_shipping_address_get_wrong_email_denied(self):
        mock_address = MagicMock()
        mock_address.email = "owner@example.com"

        with patch(
            "src.cqrs.router.ShippingAddressService"
        ) as mock_service_cls:
            mock_service_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_address
            )
            with pytest.raises(AuthorizationError):
                await CQRSRouter.execute_query(
                    "shippingAddress.get",
                    {
                        "id": "507f1f77bcf86cd799439011",
                        "email": "attacker@example.com",
                    },
                )

    @pytest.mark.asyncio
    async def test_shipping_address_get_matching_email_allowed(self):
        mock_address = MagicMock()
        mock_address.email = "owner@example.com"

        with patch(
            "src.cqrs.router.ShippingAddressService"
        ) as mock_service_cls, patch.object(
            CQRSRouter.QUERIES["shippingAddress.get"],
            "execute",
            new_callable=AsyncMock,
        ) as mock_execute:
            mock_service_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_address
            )
            mock_execute.return_value = {"data": {"email": "owner@example.com"}}

            result = await CQRSRouter.execute_query(
                "shippingAddress.get",
                {
                    "id": "507f1f77bcf86cd799439011",
                    "email": "owner@example.com",
                },
            )
            assert result["data"]["email"] == "owner@example.com"

    @pytest.mark.asyncio
    async def test_order_get_id_only_denied(self):
        with pytest.raises(AuthorizationError):
            await CQRSRouter.execute_query("order.get", {"id": "order-1"})


class TestOrderServiceDefenseInDepth:
    def test_build_order_query_rejects_operator_email(self):
        service = OrderService()
        with pytest.raises(ValueError, match="scalar value"):
            service._build_order_query(user_email={"$ne": None})
