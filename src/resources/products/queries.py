from typing import Dict, Any
from src.cqrs.base import CommandQuery
from src.services.product_service import ProductService


class ProductListQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        skip = params.get("skip", 0)
        limit = params.get("take") or params.get("limit", 20)
        active = params.get("active")
        category_id = params.get("category_id")
        include_categories = params.get("include_categories", True)
        
        products = await service.list(skip=skip, limit=limit, active=active, category_id=category_id, include_categories=include_categories)
        total = await service.count(active=active, category_id=category_id)
        return {
            "data": products,
            "count": total
        }


class ProductGetQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        product_id = params.get("id")
        
        if not product_id:
            raise ValueError("Product ID is required")
        
        product = await service.get_by_id(product_id)
        if not product:
            raise ValueError("Product not found")
        
        return {"data": product.model_dump(by_alias=True)}


class ProductSearchQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        search_term = params.get("search_term")
        skip = params.get("skip", 0)
        limit = params.get("take") or params.get("limit", 20)
        include_categories = params.get("include_categories", True)
        
        if not search_term:
            raise ValueError("Search term is required")
        
        products = await service.search(search_term, skip=skip, limit=limit, include_categories=include_categories)
        total = await service.search_count(search_term)
        return {
            "data": products,
            "count": total
        }


class ProductGetByIdsQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        product_ids = params.get("ids", [])
        include_categories = params.get("include_categories", True)
        
        if not product_ids:
            raise ValueError("Product IDs are required")
        
        if not isinstance(product_ids, list):
            raise ValueError("Product IDs must be a list")
        
        products = await service.get_by_ids(product_ids, include_categories=include_categories)
        return {
            "data": products,
            "count": len(products)
        }
