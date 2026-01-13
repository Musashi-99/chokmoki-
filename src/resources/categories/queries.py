from typing import Dict, Any
from src.cqrs.base import CommandQuery
from src.services.category_service import CategoryService
from src.models.common import ListResponseDTO, QueryResponseDTO


class CategoryListQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = CategoryService()
        skip = params.get("skip", 0)
        limit = params.get("take") or params.get("limit", 20)
        
        categories = await service.list(skip=skip, limit=limit)
        total = await service.count()
        return ListResponseDTO(
            data=[category.model_dump(by_alias=True) for category in categories],
            count=total
        ).model_dump()


class CategoryGetQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = CategoryService()
        category_id = params.get("id")
        
        if not category_id:
            raise ValueError("Category ID is required")
        
        category = await service.get_by_id(category_id)
        if not category:
            raise ValueError("Category not found")
        
        return QueryResponseDTO(data=category.model_dump(by_alias=True)).model_dump()
