from typing import Dict, Any
from src.cqrs.base import CommandMutation
from src.services.order_service import OrderService
from src.models.order import OrderCreateInput, OrderStatus


class OrderCreateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = OrderService()
        
        if "shippingAddress" not in params:
            raise ValueError("shippingAddress is required")
        if "items" not in params or not params["items"]:
            raise ValueError("items are required")
        if "userEmail" not in params:
            raise ValueError("userEmail is required")
        
        order_data = OrderCreateInput(**params)
        order = await service.create(order_data)
        return {"data": order.model_dump(by_alias=True)}


class OrderInitiateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = OrderService()
        
        if "shippingAddress" not in params:
            raise ValueError("shippingAddress is required")
        if "items" not in params or not params["items"]:
            raise ValueError("items are required")
        if "userEmail" not in params:
            raise ValueError("userEmail is required")
        
        order_data = OrderCreateInput(**params)
        result = await service.initiate_order(order_data)
        return {"data": result}


class OrderVerifyPaymentMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = OrderService()
        
        order_id = params.get("order_id")
        razorpay_order_id = params.get("razorpay_order_id")
        razorpay_payment_id = params.get("razorpay_payment_id")
        razorpay_signature = params.get("razorpay_signature")
        
        if not all([order_id, razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            raise ValueError("All payment verification fields are required")
        
        order = await service.verify_payment(
            order_id, razorpay_order_id, razorpay_payment_id, razorpay_signature
        )
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
