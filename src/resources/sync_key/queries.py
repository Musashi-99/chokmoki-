from typing import Dict, Any
from src.cqrs.base import CommandQuery
from src.services.sync_key_service import SyncKeyService
from src.models.common import QueryResponseDTO


class SyncKeyGetQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = SyncKeyService()
        key_type = params.get("key", "products")
        
        if key_type == "products":
            sync_key = await service.get_or_create_products_sync_key()
            return QueryResponseDTO(data={"key": "products", "value": sync_key}).model_dump()
        
        raise ValueError(f"Unknown sync key type: {key_type}")
