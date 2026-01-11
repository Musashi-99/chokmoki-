from typing import Dict, Any
from src.cqrs.base import CommandMutation
from src.services.product_service import ProductService
from src.services.category_service import CategoryService
from src.services.order_service import OrderService
from src.services.contact_service import ContactService
from src.services.shipping_address_service import ShippingAddressService
from src.models.product import ProductCreate
from src.models.category import CategoryCreate
from src.models.order import OrderCreate, OrderStatus
from src.models.contact import ContactCreate
from src.models.shipping_address import ShippingAddressCreate, ShippingAddressUpdate
from src.plugins.logger import logger


class ProductCreateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        product_data = ProductCreate(**params)
        product = await service.create(product_data)
        return {"data": product.model_dump(by_alias=True)}


class ProductUpdateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        product_id = params.pop("id")
        
        if not product_id:
            raise ValueError("Product ID is required")
        
        product = await service.update(product_id, params)
        if not product:
            raise ValueError("Product not found")
        
        return {"data": product.model_dump(by_alias=True)}


class ProductDeleteMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ProductService()
        product_id = params.get("id")
        
        if not product_id:
            raise ValueError("Product ID is required")
        
        success = await service.delete(product_id)
        if not success:
            raise ValueError("Product not found")
        
        return {"success": True}


class CategoryCreateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = CategoryService()
        category_data = CategoryCreate(**params)
        category = await service.create(category_data)
        return {"data": category.model_dump(by_alias=True)}


class CategoryUpdateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = CategoryService()
        category_id = params.pop("id")
        
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
        
        return {"success": True}


class OrderCreateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: Manual Clerk token validation should be done here
        # Validate clerk_token from params["shipping_details"]["clerk_token"]
        
        service = OrderService()
        order_data = OrderCreate(**params)
        order = await service.create(order_data)
        return {"data": order.model_dump(by_alias=True)}


class OrderStatusUpdateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = OrderService()
        order_id = params.get("id")
        status_data = params.get("status")
        
        if not order_id:
            raise ValueError("Order ID is required")
        if not status_data:
            raise ValueError("Status is required")
        
        status = OrderStatus(**status_data)
        order = await service.update_status(order_id, status)
        
        if not order:
            raise ValueError("Order not found")
        
        return {"data": order.model_dump(by_alias=True)}


class ContactCreateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ContactService()
        contact_data = ContactCreate(**params)
        contact = await service.create(contact_data)
        return {"data": contact.model_dump(by_alias=True)}


class ShippingAddressCreateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ShippingAddressService()
        address_data = ShippingAddressCreate(**params)
        address = await service.create(address_data)
        return {"data": address.model_dump(by_alias=True)}


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
        
        return {"data": address.model_dump(by_alias=True)}


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
        
        return {"success": True}

