from typing import Dict, Any
from src.cqrs.base import CommandQuery
from src.services.shipping_address_service import ShippingAddressService
from src.models.common import QueryResponseDTO, ListResponseDTO


class ShippingAddressListQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ShippingAddressService()
        email = params.get("email")
        
        if not email:
            raise ValueError("email is required")
        
        addresses = await service.get_by_email(email)
        return ListResponseDTO(
            data=[addr.model_dump(by_alias=True) for addr in addresses],
            count=len(addresses)
        ).model_dump()


class ShippingAddressGetQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ShippingAddressService()
        address_id = params.get("id")
        email = params.get("email")
        
        if not address_id:
            raise ValueError("Address ID is required")
        
        address = await service.get_by_id(address_id)
        if not address:
            raise ValueError("Address not found")
        
        # Verify the address belongs to the user if email is provided
        if email and address.email != email:
            raise ValueError("Address not found or access denied")
        
        return QueryResponseDTO(data=address.model_dump(by_alias=True)).model_dump()
