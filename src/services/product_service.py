from typing import List, Optional, Dict, Any
from bson import ObjectId
from src.database.connection import db
from src.models.product import Product, ProductCreate, ProductVariant, VariantValue
from src.services.category_service import CategoryService
from src.plugins.logger import logger


class ProductService:
    COLLECTION_NAME = "products"
    
    async def create(self, product_data: ProductCreate) -> Product:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        product_dict = product_data.model_dump()
        
        if not product_dict.get("product_variants"):
            product_dict["product_variants"] = [
                ProductVariant(
                    variant_name="default",
                    variant_values=[VariantValue(label="default", active=True)]
                ).model_dump()
            ]
        
        if product_dict.get("categories"):
            product_dict["categories"] = [ObjectId(cat_id) for cat_id in product_dict["categories"]]
        
        result = await collection.insert_one(product_dict)
        product_dict["_id"] = result.inserted_id
        
        logger.info(f"Product created: {result.inserted_id}")
        return Product(**product_dict)
    
    async def get_by_id(self, product_id: str) -> Optional[Product]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        product = await collection.find_one({"_id": ObjectId(product_id)})
        if product:
            return Product(**product)
        return None
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 20,
        active: Optional[bool] = None,
        category_id: Optional[str] = None,
        include_categories: bool = True
    ) -> List[Dict[str, Any]]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {}
        if active is not None:
            query["active"] = active
        if category_id:
            query["categories"] = ObjectId(category_id)
        
        cursor = collection.find(query).skip(skip).limit(limit)
        products = await cursor.to_list(length=limit)
        
        result = []
        category_service = CategoryService()
        
        for product in products:
            product_dict = Product(**product).model_dump(by_alias=True)
            
            if include_categories and product_dict.get("categories"):
                category_details = []
                for cat_id in product_dict["categories"]:
                    category = await category_service.get_by_id(str(cat_id))
                    if category:
                        category_details.append(category.model_dump(by_alias=True))
                product_dict["category_details"] = category_details
            
            result.append(product_dict)
        
        return result
    
    async def search(self, search_term: str, skip: int = 0, limit: int = 20, include_categories: bool = True) -> List[Dict[str, Any]]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query = {
            "$or": [
                {"name": {"$regex": search_term, "$options": "i"}},
                {"brand": {"$regex": search_term, "$options": "i"}},
                {"tags": {"$in": [search_term]}},
                {"product_description": {"$regex": search_term, "$options": "i"}}
            ]
        }
        
        cursor = collection.find(query).skip(skip).limit(limit)
        products = await cursor.to_list(length=limit)
        
        result = []
        category_service = CategoryService()
        
        for product in products:
            product_dict = Product(**product).model_dump(by_alias=True)
            
            if include_categories and product_dict.get("categories"):
                category_details = []
                for cat_id in product_dict["categories"]:
                    category = await category_service.get_by_id(str(cat_id))
                    if category:
                        category_details.append(category.model_dump(by_alias=True))
                product_dict["category_details"] = category_details
            
            result.append(product_dict)
        
        return result
    
    async def count(
        self,
        active: Optional[bool] = None,
        category_id: Optional[str] = None
    ) -> int:
        """Count products matching the given filters"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {}
        if active is not None:
            query["active"] = active
        if category_id:
            query["categories"] = ObjectId(category_id)
        
        return await collection.count_documents(query)
    
    async def search_count(self, search_term: str) -> int:
        """Count products matching the search term"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query = {
            "$or": [
                {"name": {"$regex": search_term, "$options": "i"}},
                {"brand": {"$regex": search_term, "$options": "i"}},
                {"tags": {"$in": [search_term]}},
                {"product_description": {"$regex": search_term, "$options": "i"}}
            ]
        }
        
        return await collection.count_documents(query)
    
    async def update(self, product_id: str, update_data: Dict[str, Any]) -> Optional[Product]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        if "categories" in update_data and update_data["categories"]:
            update_data["categories"] = [ObjectId(cat_id) for cat_id in update_data["categories"]]
        
        result = await collection.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            return await self.get_by_id(product_id)
        return None
    
    async def delete(self, product_id: str) -> bool:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        result = await collection.delete_one({"_id": ObjectId(product_id)})
        return result.deleted_count > 0
    
    async def get_by_ids(self, product_ids: List[str], include_categories: bool = True) -> List[Dict[str, Any]]:
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        object_ids = [ObjectId(pid) for pid in product_ids if ObjectId.is_valid(pid)]
        if not object_ids:
            return []
        
        cursor = collection.find({"_id": {"$in": object_ids}})
        products = await cursor.to_list(length=len(object_ids))
        
        result = []
        category_service = CategoryService()
        
        for product in products:
            product_dict = Product(**product).model_dump(by_alias=True)
            
            if include_categories and product_dict.get("categories"):
                category_details = []
                for cat_id in product_dict["categories"]:
                    category = await category_service.get_by_id(str(cat_id))
                    if category:
                        category_details.append(category.model_dump(by_alias=True))
                product_dict["category_details"] = category_details
            
            result.append(product_dict)
        
        return result

