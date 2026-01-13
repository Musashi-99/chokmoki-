from typing import Dict, Any
from src.cqrs.base import CommandQuery
from src.services.rating_service import RatingService


class RatingListQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = RatingService()
        product_id = params.get("product_id") or params.get("productId")
        skip = params.get("skip", 0)
        limit = params.get("limit", 20) or params.get("take", 20)
        
        if not product_id:
            raise ValueError("product_id is required")
        
        ratings, total = await service.get_by_product(product_id, skip=skip, limit=limit)
        
        return {
            "data": [rating.model_dump(by_alias=True) for rating in ratings],
            "count": total
        }


class RatingSummaryQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = RatingService()
        product_id = params.get("product_id") or params.get("productId")
        
        if not product_id:
            raise ValueError("product_id is required")
        
        summary = await service.get_summary(product_id)
        return {"data": summary}


class RatingCanRateQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = RatingService()
        order_id = params.get("order_id") or params.get("orderId")
        product_id = params.get("product_id") or params.get("productId")
        email = params.get("email")
        
        if not order_id or not product_id or not email:
            raise ValueError("order_id, product_id, and email are required")
        
        can_rate = await service.check_user_can_rate(order_id, product_id, email)
        return {"data": {"can_rate": can_rate}}
