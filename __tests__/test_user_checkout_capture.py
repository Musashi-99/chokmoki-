from __future__ import annotations

import copy
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pymongo.errors import DuplicateKeyError

os.environ.setdefault("ENVIRONMENT", "development")
os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.user import User, UserProfileUpdate
from src.services.user_service import UserService, address_identity, normalize_phone


class FakeUsers:
    def __init__(self, docs=None):
        self.docs = [copy.deepcopy(d) for d in (docs or [])]

    def _match(self, doc, query):
        for key, value in query.items():
            if "." in key:
                head, _, tail = key.partition(".")
                nested = doc.get(head) or []
                if not any(isinstance(item, dict) and item.get(tail) == value for item in nested):
                    return False
            elif doc.get(key) != value:
                return False
        return True

    async def find_one(self, query):
        for doc in self.docs:
            if self._match(doc, query):
                return copy.deepcopy(doc)
        return None

    async def insert_one(self, doc):
        incoming = copy.deepcopy(doc)
        if incoming.get("phone") and any(d.get("phone") == incoming["phone"] for d in self.docs):
            raise DuplicateKeyError("E11000 phone")
        if incoming.get("email") and any(d.get("email") == incoming["email"] for d in self.docs):
            raise DuplicateKeyError("E11000 email")
        self.docs.append(incoming)
        return SimpleNamespace(inserted_id="1")

    async def update_one(self, query, update):
        for doc in self.docs:
            if not self._match(doc, query):
                continue
            for key, value in (update.get("$set") or {}).items():
                if key == "addresses.$[].is_default":
                    for addr in doc.get("addresses") or []:
                        addr["is_default"] = value
                elif key == "addresses.$":
                    aid = query.get("addresses.id")
                    addrs = doc.get("addresses") or []
                    for i, addr in enumerate(addrs):
                        if addr.get("id") == aid:
                            addrs[i] = value
                else:
                    doc[key] = value
            for key, value in (update.get("$push") or {}).items():
                doc.setdefault(key, []).append(copy.deepcopy(value))
            for key, value in (update.get("$pull") or {}).items():
                doc[key] = [
                    item
                    for item in (doc.get(key) or [])
                    if not all(item.get(k) == v for k, v in value.items())
                ]
            return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


def _db(col: FakeUsers):
    return AsyncMock(return_value={"users": col})


CHECKOUT = dict(
    full_name="Priya Sen",
    phone="9876543210",
    email="priya@example.com",
    address_line1="12 Park Street",
    city="Kolkata",
    state="West Bengal",
    postal_code="700016",
    country="India",
)


@pytest.mark.asyncio
async def test_creates_unverified_user_with_profile_and_address():
    col = FakeUsers()
    with patch("src.services.user_service.db.get_database", new=_db(col)):
        user_id = await UserService().capture_from_checkout(**CHECKOUT)

    assert user_id
    stored = col.docs[0]
    assert stored["id"] == user_id
    assert stored["phone"] == "9876543210"
    assert stored["email"] == "priya@example.com"
    assert stored["name"] == "Priya Sen"
    assert stored["phone_verified"] is False
    assert stored["email_verified"] is False
    assert len(stored["addresses"]) == 1
    assert stored["addresses"][0]["address_line1"] == "12 Park Street"
    assert stored["addresses"][0]["is_default"] is True


@pytest.mark.asyncio
async def test_reuses_phone_account_and_fills_missing_fields():
    existing = User(phone="9876543210", phone_verified=True, name=None, email=None)
    col = FakeUsers([existing.model_dump()])
    with patch("src.services.user_service.db.get_database", new=_db(col)):
        user_id = await UserService().capture_from_checkout(**CHECKOUT)

    assert user_id == existing.id
    stored = col.docs[0]
    assert stored["name"] == "Priya Sen"
    assert stored["email"] == "priya@example.com"
    assert len(stored["addresses"]) == 1


@pytest.mark.asyncio
async def test_does_not_overwrite_existing_name_or_duplicate_address():
    existing = User(
        phone="9876543210",
        name="Old Name",
        email="old@example.com",
        addresses=[],
    )
    col = FakeUsers([existing.model_dump()])
    with patch("src.services.user_service.db.get_database", new=_db(col)):
        service = UserService()
        await service.capture_from_checkout(**CHECKOUT)
        await service.capture_from_checkout(**CHECKOUT)

    stored = col.docs[0]
    assert stored["name"] == "Old Name"
    assert stored["email"] == "old@example.com"
    assert len(stored["addresses"]) == 1


@pytest.mark.asyncio
async def test_logged_in_user_wins_over_phone_match():
    logged_in = User(email="logged@example.com", name="Logged In")
    other = User(phone="9876543210", name="Someone Else")
    col = FakeUsers([logged_in.model_dump(), other.model_dump()])
    with patch("src.services.user_service.db.get_database", new=_db(col)):
        user_id = await UserService().capture_from_checkout(
            **CHECKOUT, existing_user_id=logged_in.id
        )

    assert user_id == logged_in.id
    logged_doc = next(d for d in col.docs if d["id"] == logged_in.id)
    other_doc = next(d for d in col.docs if d["id"] == other.id)
    assert len(logged_doc["addresses"]) == 1
    assert other_doc["addresses"] == []


@pytest.mark.asyncio
async def test_skips_email_claimed_by_another_account():
    owner = User(email="priya@example.com", phone="1111111111")
    guest = User(phone="9876543210")
    col = FakeUsers([owner.model_dump(), guest.model_dump()])
    with patch("src.services.user_service.db.get_database", new=_db(col)):
        user_id = await UserService().capture_from_checkout(**CHECKOUT)

    assert user_id == guest.id
    guest_doc = next(d for d in col.docs if d["id"] == guest.id)
    assert guest_doc.get("email") in (None, "")


@pytest.mark.asyncio
async def test_email_signup_starts_with_phone_unverified():
    col = FakeUsers()
    with patch("src.services.user_service.db.get_database", new=_db(col)):
        user = await UserService().get_or_create_by_email("buyer@example.com")
    assert user.phone_verified is False


@pytest.mark.asyncio
async def test_profile_phone_change_clears_verification():
    existing = User(
        email="buyer@example.com",
        email_verified=True,
        phone=None,
        phone_verified=False,
    )
    col = FakeUsers([existing.model_dump()])
    with patch("src.services.user_service.db.get_database", new=_db(col)):
        updated = await UserService().update_profile(
            existing.id, UserProfileUpdate(phone="9876543210")
        )
    assert updated is not None
    assert updated.phone == "9876543210"
    assert updated.phone_verified is False


def test_address_identity_and_phone_normalize():
    assert address_identity("12  Park Street", "700016") == address_identity(
        "12 park street", "700016"
    )
    assert normalize_phone("+91 98765-43210") == "9876543210"
