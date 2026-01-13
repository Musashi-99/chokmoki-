from typing import Dict, Any
from src.cqrs.base import CommandMutation
from src.services.rating_service import RatingService
from src.models.rating import RatingCreate


class RatingCreateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = RatingService()
        
        # Map params to RatingCreate model
        rating_data = RatingCreate(
            order_id=params.get("order_id") or params.get("orderId"),
            product_id=params.get("product_id") or params.get("productId"),
            email=params.get("email"),
            rating=params.get("rating"),
            comment=params.get("comment", "")
        )
        
        rating = await service.create(rating_data)
        return {"data": rating.model_dump(by_alias=True)}
