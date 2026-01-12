from typing import Dict, Any
from src.cqrs.base import CommandMutation
from src.services.order_service import OrderService
from src.models.order import OrderCreateInput, OrderStatus


class OrderCreateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = OrderService()
        
        # Validate required fields
        if "shippingAddress" not in params:
            raise ValueError("shippingAddress is required")
        if "items" not in params or not params["items"]:
            raise ValueError("items are required")
        if "userEmail" not in params:
            raise ValueError("userEmail is required")
        
        # Create order with validation
        order_data = OrderCreateInput(**params)
        order = await service.create(order_data)
        return {"data": order.model_dump(by_alias=True)}


class OrderStatusUpdateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = OrderService()
        order_id = params.get("order_id") or params.get("id")
        status_data = params.get("status")
        
        if not order_id:
            raise ValueError("order_id is required")
        if not status_data:
            raise ValueError("Status is required")
        
        status = OrderStatus(**status_data)
        order = await service.update_status(order_id, status)
        
        if not order:
            raise ValueError("Order not found")
        
        return {"data": order.model_dump(by_alias=True)}
