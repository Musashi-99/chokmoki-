from typing import Dict, Any
from src.cqrs.base import CommandQuery
from src.services.order_service import OrderService
from src.models.common import ListResponseDTO, QueryResponseDTO


class OrderListQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = OrderService()
        skip = params.get("skip", 0)
        limit = params.get("limit", 20)
        user_email = params.get("userEmail")
        status = params.get("status")
        search = params.get("search")
        from_date = params.get("fromDate")
        to_date = params.get("toDate")
        sort_order = params.get("sortOrder", -1)
        
        orders = await service.list(
            skip=skip, limit=limit, user_email=user_email,
            status=status, search=search,
            from_date=from_date, to_date=to_date, sort_order=sort_order
        )
        total = await service.count(
            user_email=user_email, status=status,
            search=search, from_date=from_date, to_date=to_date
        )
        return ListResponseDTO(
            data=[order.model_dump(by_alias=True) for order in orders],
            count=total
        ).model_dump()


class OrderGetQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = OrderService()
        order_id = params.get("id")
        
        if not order_id:
            raise ValueError("Order ID is required")
        
        order = await service.get_by_id(order_id)
        if not order:
            raise ValueError("Order not found")
        
        return QueryResponseDTO(data=order.model_dump(by_alias=True)).model_dump()


class OrderLogQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = OrderService()
        order_id = params.get("order_id")
        
        if not order_id:
            raise ValueError("order_id is required")
        
        log = await service.get_order_log(order_id)
        if not log:
            raise ValueError("Order log not found")
        
        return QueryResponseDTO(data=log.model_dump()).model_dump()
