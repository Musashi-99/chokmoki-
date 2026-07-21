from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from src.database.connection import db
from src.models.sms_template import LIFECYCLE_TEMPLATE_KEYS, SmsTemplate, SmsTemplateUpdate

COLLECTION_NAME = "sms_templates"

_DEFAULT_DESCRIPTIONS = {
    "order_placed": "Sent when a customer's order is confirmed.",
    "order_shipped": "Sent when a shipment is picked up by the courier.",
    "order_out_for_delivery": "Sent when the courier marks the shipment out for delivery.",
    "order_delivered": "Sent when the shipment is marked delivered.",
    "order_cancelled": "Sent when an order/shipment is cancelled.",
}


class SmsTemplateService:
    async def ensure_indexes(self) -> None:
        database = await db.get_database()
        await database[COLLECTION_NAME].create_index("key", unique=True)

    async def seed_defaults(self) -> None:
        """Insert disabled placeholder rows for the known lifecycle keys so
        the admin panel has something to fill in instead of starting blank.
        Never overwrites an existing row (upsert-if-absent only).
        """
        database = await db.get_database()
        collection = database[COLLECTION_NAME]
        for key in LIFECYCLE_TEMPLATE_KEYS:
            existing = await collection.find_one({"key": key})
            if existing:
                continue
            template = SmsTemplate(
                key=key,
                enabled=False,
                description=_DEFAULT_DESCRIPTIONS.get(key, ""),
                variables=["order_id", "customer_name"],
            )
            await collection.insert_one(template.model_dump())

    async def list_all(self) -> List[SmsTemplate]:
        database = await db.get_database()
        docs = await database[COLLECTION_NAME].find({}).sort("key", 1).to_list(length=200)
        return [SmsTemplate(**doc) for doc in docs]

    async def get_by_key(self, key: str) -> Optional[SmsTemplate]:
        database = await db.get_database()
        doc = await database[COLLECTION_NAME].find_one({"key": key})
        return SmsTemplate(**doc) if doc else None

    async def upsert(self, key: str, update: SmsTemplateUpdate, *, actor_email: str) -> SmsTemplate:
        database = await db.get_database()
        collection = database[COLLECTION_NAME]
        patch = {k: v for k, v in update.model_dump(exclude_unset=True).items()}
        patch["updated_at"] = datetime.utcnow()
        patch["updated_by"] = actor_email
        await collection.update_one(
            {"key": key},
            {"$set": patch, "$setOnInsert": {"key": key}},
            upsert=True,
        )
        doc = await collection.find_one({"key": key})
        return SmsTemplate(**doc)
