from typing import Dict, Any
from src.cqrs.base import CommandQuery
from src.services.shipping_address_service import ShippingAddressService
from src.models.common import QueryResponseDTO, ListResponseDTO
from src.security.exceptions import AuthorizationError


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
        if not email:
            raise AuthorizationError("Authentication required to view this address")

        address = await service.get_by_id(address_id)
        if not address:
            raise ValueError("Address not found")

        if address.email.lower() != str(email).strip().lower():
            raise AuthorizationError("Authentication required to view this address")

        return QueryResponseDTO(data=address.model_dump(by_alias=True)).model_dump()
