from typing import Dict, Any
from src.cqrs.base import CommandMutation
from src.services.category_service import CategoryService
from src.models.category import JewelryCategoryCreate
from src.models.common import MutationResponseDTO


class CategoryCreateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = CategoryService()
        category_data = JewelryCategoryCreate(**params)
        category = await service.create(category_data)
        return MutationResponseDTO(data=category.model_dump(by_alias=True)).model_dump()


class CategoryUpdateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = CategoryService()
        category_id = params.pop("id", None)
        
        if not category_id:
            raise ValueError("Category ID is required")
        
        category = await service.update(category_id, params)
        if not category:
            raise ValueError("Category not found")
        
        return {"data": category.model_dump(by_alias=True)}


class CategoryDeleteMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = CategoryService()
        category_id = params.get("id")
        
        if not category_id:
            raise ValueError("Category ID is required")
        
        success = await service.delete(category_id)
        if not success:
            raise ValueError("Category not found")
        
        return MutationResponseDTO(success=True).model_dump()
