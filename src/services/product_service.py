from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from src.database.connection import db
from src.models.product import JewelryProduct, JewelryProductCreate
from src.plugins.logger import logger


class ProductService:
    COLLECTION_NAME = "products"

    async def _collection(self):
        database = await db.get_database()
        return database[self.COLLECTION_NAME]

    async def _resolve_filter(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Resolve a Mongo filter from an ObjectId string or product slug."""
        collection = await self._collection()
        product_id = str(product_id).strip()
        if not product_id:
            return None

        if ObjectId.is_valid(product_id):
            filt = {"_id": ObjectId(product_id)}
            if await collection.find_one(filt, {"_id": 1}):
                return filt

        doc = await collection.find_one({"slug": product_id}, {"_id": 1})
        if doc:
            return {"_id": doc["_id"]}
        return None
    
    async def create(self, product_data: JewelryProductCreate) -> JewelryProduct:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]

        existing = await collection.find_one({"slug": product_data.slug})
        if existing:
            raise ValueError(f"Product with slug '{product_data.slug}' already exists")

        product_dict = product_data.model_dump()
        if product_dict.get("category"):
            product_dict["category"] = str(product_dict["category"]).strip().lower()
        if product_dict.get("slug"):
            product_dict["slug"] = str(product_dict["slug"]).strip().lower()
        product_dict["created_at"] = datetime.utcnow()
        result = await collection.insert_one(product_dict)
        product_dict["_id"] = result.inserted_id

        logger.info(f"Product created: {result.inserted_id}")
        return JewelryProduct(**product_dict)

    async def upsert_by_slug(self, product_data: JewelryProductCreate) -> JewelryProduct:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]

        product_dict = product_data.model_dump()
        now = datetime.utcnow()
        await collection.update_one(
            {"slug": product_data.slug},
            {
                "$set": {**product_dict, "active": product_data.active},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        saved = await collection.find_one({"slug": product_data.slug})
        logger.info(f"Product upserted: {product_data.slug}")
        return JewelryProduct(**saved)
    
    async def get_by_id(self, product_id: str) -> Optional[JewelryProduct]:
        filt = await self._resolve_filter(product_id)
        if not filt:
            return await self.get_by_slug(product_id)

        collection = await self._collection()
        product = await collection.find_one(filt)
        if product:
            return JewelryProduct(**product)
        return None
    
    async def get_by_slug(self, slug: str) -> Optional[JewelryProduct]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        product = await collection.find_one({"slug": slug})
        if product:
            return JewelryProduct(**product)
        return None
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 50,
        active: Optional[bool] = None,
        category: Optional[str] = None,
        is_best_seller: Optional[bool] = None,
        is_curated: Optional[bool] = None,
        sort: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {}
        if active is not None:
            query["active"] = active
        if category:
            query["category"] = category
        if is_best_seller is not None:
            query["is_best_seller"] = is_best_seller
        if is_curated is not None:
            query["is_curated"] = is_curated
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}},
                {"material": {"$regex": search, "$options": "i"}},
                {"slug": {"$regex": search, "$options": "i"}},
            ]
        
        cursor = collection.find(query)
        
        if is_best_seller:
            cursor = cursor.sort([("best_seller_order", 1), ("created_at", -1)])
        elif is_curated:
            cursor = cursor.sort([("curated_order", 1), ("created_at", -1)])
        elif sort == "low":
            cursor = cursor.sort("price_inr", 1)
        elif sort == "high":
            cursor = cursor.sort("price_inr", -1)
        else:
            cursor = cursor.sort("created_at", -1)
        
        cursor = cursor.skip(skip).limit(limit)
        products = await cursor.to_list(length=limit)
        
        return [JewelryProduct(**product).model_dump(by_alias=True) for product in products]
    
    async def count(
        self,
        active: Optional[bool] = None,
        category: Optional[str] = None,
        is_best_seller: Optional[bool] = None,
        is_curated: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> int:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {}
        if active is not None:
            query["active"] = active
        if category:
            query["category"] = category
        if is_best_seller is not None:
            query["is_best_seller"] = is_best_seller
        if is_curated is not None:
            query["is_curated"] = is_curated
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}},
                {"material": {"$regex": search, "$options": "i"}},
                {"slug": {"$regex": search, "$options": "i"}},
            ]
        
        return await collection.count_documents(query)
    
    async def update(self, product_id: str, update_data: Dict[str, Any]) -> Optional[JewelryProduct]:
        collection = await self._collection()
        product_filter = await self._resolve_filter(product_id)
        if not product_filter:
            return None

        protected = {"_id", "id", "created_at"}
        payload = {k: v for k, v in update_data.items() if k not in protected}
        if not payload:
            return await self.get_by_id(product_id)

        if "category" in payload and payload["category"]:
            payload["category"] = str(payload["category"]).strip().lower()
        if "slug" in payload and payload["slug"]:
            payload["slug"] = str(payload["slug"]).strip().lower()
            existing = await collection.find_one({
                "slug": payload["slug"],
                "_id": {"$ne": product_filter["_id"]},
            })
            if existing:
                raise ValueError(f"Product with slug '{payload['slug']}' already exists")

        result = await collection.update_one(product_filter, {"$set": payload})

        if result.matched_count == 0:
            return None
        saved = await collection.find_one(product_filter)
        return JewelryProduct(**saved) if saved else None
    
    async def delete(self, product_id: str) -> bool:
        product_filter = await self._resolve_filter(product_id)
        if not product_filter:
            return False

        collection = await self._collection()
        result = await collection.delete_one(product_filter)
        return result.deleted_count > 0
    
    async def get_by_slugs(self, slugs: List[str]) -> List[Dict[str, Any]]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        cursor = collection.find({"slug": {"$in": slugs}})
        products = await cursor.to_list(length=len(slugs))
        
        return [JewelryProduct(**product).model_dump(by_alias=True) for product in products]
