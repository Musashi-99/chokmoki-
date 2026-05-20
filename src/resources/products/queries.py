from typing import Dict, Any
from src.cqrs.base import CommandQuery
from src.services.product_service import ProductService
from src.models.common import ListResponseDTO, QueryResponseDTO


class ProductListQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        skip = params.get("skip", 0)
        limit = params.get("take") or params.get("limit", 50)
        active = params.get("active")
        category = params.get("category")
        sort = params.get("sort")
        search = params.get("search")
        
        products = await service.list(skip=skip, limit=limit, active=active, category=category, sort=sort, search=search)
        total = await service.count(active=active, category=category, search=search)
        return ListResponseDTO(data=products, count=total).model_dump()


class ProductGetQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        product_id = params.get("id")
        slug = params.get("slug")
        
        if slug:
            product = await service.get_by_slug(slug)
        elif product_id:
            product = await service.get_by_id(product_id)
        else:
            raise ValueError("Product ID or slug is required")
        
        if not product:
            raise ValueError("Product not found")
        
        return QueryResponseDTO(data=product.model_dump(by_alias=True)).model_dump()


class ProductSearchQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        search_term = params.get("search_term") or params.get("search")
        skip = params.get("skip", 0)
        limit = params.get("take") or params.get("limit", 50)
        
        if not search_term:
            raise ValueError("Search term is required")
        
        products = await service.list(skip=skip, limit=limit, search=search_term)
        total = await service.count(search=search_term)
        return ListResponseDTO(data=products, count=total).model_dump()


class ProductGetByIdsQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        product_ids = params.get("ids", [])
        slugs = params.get("slugs", [])
        
        if slugs:
            products = await service.get_by_slugs(slugs)
            return ListResponseDTO(data=products, count=len(products)).model_dump()
        
        if not product_ids:
            raise ValueError("Product IDs or slugs are required")
        
        if not isinstance(product_ids, list):
            raise ValueError("Product IDs must be a list")
        
        products = []
        for pid in product_ids:
            product = await service.get_by_id(pid)
            if product:
                products.append(product.model_dump(by_alias=True))
        
        return ListResponseDTO(data=products, count=len(products)).model_dump()
