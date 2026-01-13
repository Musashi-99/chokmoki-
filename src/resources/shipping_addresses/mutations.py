from typing import Dict, Any
from src.cqrs.base import CommandMutation
from src.services.shipping_address_service import ShippingAddressService
from src.models.shipping_address import ShippingAddressCreate, ShippingAddressUpdate
from src.models.common import MutationResponseDTO


class ShippingAddressCreateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ShippingAddressService()
        address_data = ShippingAddressCreate(**params)
        address = await service.create(address_data)
        return MutationResponseDTO(data=address.model_dump(by_alias=True)).model_dump()


class ShippingAddressUpdateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ShippingAddressService()
        address_id = params.pop("id")
        email = params.pop("email")
        
        if not address_id:
            raise ValueError("Address ID is required")
        if not email:
            raise ValueError("Email is required")
        
        update_data = ShippingAddressUpdate(**params)
        address = await service.update(address_id, update_data, email)
        if not address:
            raise ValueError("Address not found or access denied")
        
        return MutationResponseDTO(data=address.model_dump(by_alias=True)).model_dump()


class ShippingAddressDeleteMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ShippingAddressService()
        address_id = params.get("id")
        email = params.get("email")
        
        if not address_id:
            raise ValueError("Address ID is required")
        if not email:
            raise ValueError("Email is required")
        
        success = await service.delete(address_id, email)
        if not success:
            raise ValueError("Address not found or access denied")
        
        return MutationResponseDTO(success=True).model_dump()
