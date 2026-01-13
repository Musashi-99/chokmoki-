from typing import Dict, Any
from src.cqrs.base import CommandMutation
from src.services.product_service import ProductService
from src.services.sync_key_service import SyncKeyService
from src.models.product import ProductCreate
from src.models.common import MutationResponseDTO


class ProductCreateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        product_data = ProductCreate(**params)
        product = await service.create(product_data)
        
        sync_key_service = SyncKeyService()
        await sync_key_service.update_products_sync_key()
        
        return MutationResponseDTO(data=product.model_dump(by_alias=True)).model_dump()


class ProductUpdateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        product_id = params.pop("id")
        
        if not product_id:
            raise ValueError("Product ID is required")
        
        product = await service.update(product_id, params)
        if not product:
            raise ValueError("Product not found")
        
        sync_key_service = SyncKeyService()
        await sync_key_service.update_products_sync_key()
        
        return MutationResponseDTO(data=product.model_dump(by_alias=True)).model_dump()


class ProductDeleteMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        product_id = params.get("id")
        
        if not product_id:
            raise ValueError("Product ID is required")
        
        success = await service.delete(product_id)
        if not success:
            raise ValueError("Product not found")
        
        sync_key_service = SyncKeyService()
        await sync_key_service.update_products_sync_key()
        
        return MutationResponseDTO(success=True).model_dump()
