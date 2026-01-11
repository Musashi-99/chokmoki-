from typing import Dict, Any, List
from src.cqrs.base import CommandQuery
from src.services.product_service import ProductService
from src.services.category_service import CategoryService
from src.services.order_service import OrderService
from src.plugins.logger import logger


class ProductListQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        skip = params.get("skip", 0)
        limit = params.get("limit", 20)
        active = params.get("active")
        category_id = params.get("category_id")
        include_categories = params.get("include_categories", True)
        
        products = await service.list(skip=skip, limit=limit, active=active, category_id=category_id, include_categories=include_categories)
        return {
            "data": products,
            "count": len(products)
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
        limit = params.get("limit", 20)
        include_categories = params.get("include_categories", True)
        
        if not search_term:
            raise ValueError("Search term is required")
        
        products = await service.search(search_term, skip=skip, limit=limit, include_categories=include_categories)
        return {
            "data": products,
            "count": len(products)
        }


class CategoryListQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = CategoryService()
        skip = params.get("skip", 0)
        limit = params.get("limit", 20)
        
        categories = await service.list(skip=skip, limit=limit)
        return {
            "data": [category.model_dump(by_alias=True) for category in categories],
            "count": len(categories)
        }


class CategoryGetQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = CategoryService()
        category_id = params.get("id")
        
        if not category_id:
            raise ValueError("Category ID is required")
        
        category = await service.get_by_id(category_id)
        if not category:
            raise ValueError("Category not found")
        
        return {"data": category.model_dump(by_alias=True)}


class OrderListQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = OrderService()
        skip = params.get("skip", 0)
        limit = params.get("limit", 20)
        
        orders = await service.list(skip=skip, limit=limit)
        return {
            "data": [order.model_dump(by_alias=True) for order in orders],
            "count": len(orders)
        }


class OrderGetQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = OrderService()
        order_id = params.get("id")
        
        if not order_id:
            raise ValueError("Order ID is required")
        
        order = await service.get_by_id(order_id)
        if not order:
            raise ValueError("Order not found")
        
        return {"data": order.model_dump(by_alias=True)}

