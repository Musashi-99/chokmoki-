from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from src.database.connection import db
from src.models.user import Address, AddressInput, User, UserProfileUpdate

COLLECTION_NAME = "users"


def normalize_phone(raw: str) -> str:
    """Normalize to a bare 10-digit Indian mobile number (no +91/spaces/
    dashes) — the same shape shipping_address.phone is stored in on Order
    docs, so lookups against `orders.shipping_address.phone` match directly.
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


class UserService:
    async def ensure_indexes(self) -> None:
        database = await db.get_database()
        await database[COLLECTION_NAME].create_index("phone", unique=True)

    async def get_by_id(self, user_id: str) -> Optional[User]:
        database = await db.get_database()
        doc = await database[COLLECTION_NAME].find_one({"id": user_id})
        return User(**doc) if doc else None

    async def get_by_phone(self, phone: str) -> Optional[User]:
        database = await db.get_database()
        doc = await database[COLLECTION_NAME].find_one({"phone": normalize_phone(phone)})
        return User(**doc) if doc else None

    async def get_or_create_by_phone(self, phone: str) -> User:
        phone = normalize_phone(phone)
        database = await db.get_database()
        collection = database[COLLECTION_NAME]
        now = datetime.utcnow()

        existing = await collection.find_one({"phone": phone})
        if existing:
            await collection.update_one(
                {"phone": phone}, {"$set": {"last_login_at": now}}
            )
            existing["last_login_at"] = now
            return User(**existing)

        user = User(phone=phone, last_login_at=now)
        doc = user.model_dump()
        try:
            await collection.insert_one(doc)
        except Exception:
            # Concurrent first-login race (double-tap verify) — the unique
            # index on phone is the actual guard; fall back to the doc that
            # won instead of erroring the second request.
            existing = await collection.find_one({"phone": phone})
            if existing:
                return User(**existing)
            raise
        return user

    async def update_profile(self, user_id: str, update: UserProfileUpdate) -> Optional[User]:
        database = await db.get_database()
        collection = database[COLLECTION_NAME]
        patch = {k: v for k, v in update.model_dump(exclude_unset=True).items()}
        if not patch:
            return await self.get_by_id(user_id)
        patch["updated_at"] = datetime.utcnow()
        await collection.update_one({"id": user_id}, {"$set": patch})
        return await self.get_by_id(user_id)

    async def add_address(self, user_id: str, payload: AddressInput) -> Optional[User]:
        database = await db.get_database()
        collection = database[COLLECTION_NAME]
        address = Address(**payload.model_dump())
        if address.is_default:
            await collection.update_one(
                {"id": user_id}, {"$set": {"addresses.$[].is_default": False}}
            )
        await collection.update_one(
            {"id": user_id},
            {"$push": {"addresses": address.model_dump()}, "$set": {"updated_at": datetime.utcnow()}},
        )
        return await self.get_by_id(user_id)

    async def update_address(
        self, user_id: str, address_id: str, payload: AddressInput
    ) -> Optional[User]:
        database = await db.get_database()
        collection = database[COLLECTION_NAME]
        address = Address(id=address_id, **payload.model_dump())
        if address.is_default:
            await collection.update_one(
                {"id": user_id}, {"$set": {"addresses.$[].is_default": False}}
            )
        result = await collection.update_one(
            {"id": user_id, "addresses.id": address_id},
            {"$set": {"addresses.$": address.model_dump(), "updated_at": datetime.utcnow()}},
        )
        if result.matched_count == 0:
            return None
        return await self.get_by_id(user_id)

    async def delete_address(self, user_id: str, address_id: str) -> Optional[User]:
        database = await db.get_database()
        collection = database[COLLECTION_NAME]
        await collection.update_one(
            {"id": user_id},
            {"$pull": {"addresses": {"id": address_id}}, "$set": {"updated_at": datetime.utcnow()}},
        )
        return await self.get_by_id(user_id)
