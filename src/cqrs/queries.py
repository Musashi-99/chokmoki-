from typing import Dict, Any
from src.cqrs.base import CommandQuery
from src.services.sync_key_service import SyncKeyService
from src.services.shipping_address_service import ShippingAddressService
from src.services.contact_service import ContactService


class SyncKeyGetQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = SyncKeyService()
        key_type = params.get("key", "products")
        
        if key_type == "products":
            sync_key = await service.get_or_create_products_sync_key()
            return {"data": {"key": "products", "value": sync_key}}
        
        raise ValueError(f"Unknown sync key type: {key_type}")


class ShippingAddressListQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ShippingAddressService()
        email = params.get("email")
        
        if not email:
            raise ValueError("email is required")
        
        addresses = await service.get_by_email(email)
        return {
            "data": [addr.model_dump(by_alias=True) for addr in addresses],
            "count": len(addresses)
        }


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
        
        return {"data": address.model_dump(by_alias=True)}


class ContactListQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ContactService()
        skip = params.get("skip", 0)
        limit = params.get("take") or params.get("limit", 20)
        
        contacts = await service.list(skip=skip, limit=limit)
        total = await service.count()
        
        return {
            "data": [contact.model_dump(by_alias=True) for contact in contacts],
            "count": total
        }
