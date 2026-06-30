"""Manual fraud review queue backed by MongoDB."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from src.database.connection import db
from src.fraud.models import FraudContext, FraudDecision


class FraudReviewService:
    COLLECTION_NAME = "fraud_review_queue"

    async def ensure_indexes(self) -> None:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        await collection.create_index("status")
        await collection.create_index("created_at")
        await collection.create_index("decision.correlation_id")

    async def enqueue(
        self, *, ctx: FraudContext, decision: FraudDecision, payload: Dict[str, Any]
    ) -> str:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        doc = {
            "status": "pending",
            "decision": decision.model_dump(),
            "request": {
                "correlation_id": ctx.correlation_id,
                "request_id": ctx.request_id,
                "ip": ctx.ip,
                "endpoint": ctx.endpoint,
                "event_type": ctx.event_type,
                "email": ctx.email,
                "phone": ctx.phone,
                "amount": ctx.amount,
            },
            "payload_snapshot": {
                "userEmail": payload.get("userEmail") or payload.get("user_email"),
                "paymentMethod": payload.get("paymentMethod") or payload.get("payment_method"),
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await collection.insert_one(doc)
        return str(result.inserted_id)

    async def list_pending(self, *, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        cursor = (
            collection.find({"status": "pending"})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        rows = await cursor.to_list(length=limit)
        for row in rows:
            row["_id"] = str(row["_id"])
        return rows

    async def resolve(self, review_id: str, *, status: str, note: str = "") -> bool:
        if status not in {"approved", "rejected"}:
            raise ValueError("status must be approved or rejected")
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        filt = {"_id": ObjectId(review_id)} if ObjectId.is_valid(review_id) else {"_id": review_id}
        result = await collection.update_one(
            filt,
            {
                "$set": {
                    "status": status,
                    "resolution_note": note,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.matched_count > 0
