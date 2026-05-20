from typing import Dict, Any
from src.cqrs.base import CommandQuery
from src.services.category_service import CategoryService
from src.models.common import ListResponseDTO, QueryResponseDTO


class CategoryListQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = CategoryService()
        skip = params.get("skip", 0)
        limit = params.get("take") or params.get("limit", 20)
        active = params.get("active")
        
        categories = await service.list(skip=skip, limit=limit, active=active)
        total = await service.count(active=active)
        return ListResponseDTO(
            data=[category.model_dump(by_alias=True) for category in categories],
            count=total
        ).model_dump()


class CategoryGetQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = CategoryService()
        category_id = params.get("id")
        slug = params.get("slug")
        
        if slug:
            category = await service.get_by_slug(slug)
        elif category_id:
            category = await service.get_by_id(category_id)
        else:
            raise ValueError("Category ID or slug is required")
        
        if not category:
            raise ValueError("Category not found")
        
        return QueryResponseDTO(data=category.model_dump(by_alias=True)).model_dump()
