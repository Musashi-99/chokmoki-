from typing import Dict, Any, Optional, Tuple
from src.cqrs.base import CommandQuery
from src.services.analytics_service import AnalyticsService
from datetime import datetime, timedelta


class AnalyticsQueryMixin:
    """Mixin for flexible filtering and date range handling"""
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            return None
    
    def _get_date_range(self, params: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[datetime]]:
        start_date = self._parse_date(params.get("start_date"))
        end_date = self._parse_date(params.get("end_date"))
        
        # Default to last 24h if no dates provided
        if not start_date and not end_date:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=1)
        
        return start_date, end_date


class GetEventsQuery(CommandQuery, AnalyticsQueryMixin):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = AnalyticsService()
        start_date, end_date = self._get_date_range(params)
        
        events = await service.get_events(
            event_type=params.get("event_type"),
            start_date=start_date,
            end_date=end_date,
            user_id=params.get("user_id"),
            limit=params.get("limit", 100),
            skip=params.get("skip", 0)
        )
        
        return {
            "data": [event.model_dump(by_alias=True) for event in events],
            "count": len(events)
        }


class GetUniqueUsersQuery(CommandQuery, AnalyticsQueryMixin):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = AnalyticsService()
        start_date, end_date = self._get_date_range(params)
        
        count = await service.get_unique_users(start_date=start_date, end_date=end_date)
        
        return {"data": {"unique_users": count}}


class GetEventCountQuery(CommandQuery, AnalyticsQueryMixin):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = AnalyticsService()
        event_type = params.get("event_type")
        if not event_type:
            raise ValueError("event_type is required")
        
        start_date, end_date = self._get_date_range(params)
        
        count = await service.get_event_count(
            event_type=event_type,
            start_date=start_date,
            end_date=end_date
        )
        
        return {"data": {"event_type": event_type, "count": count}}


class GetRevenueQuery(CommandQuery, AnalyticsQueryMixin):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = AnalyticsService()
        start_date, end_date = self._get_date_range(params)
        
        revenue = await service.get_revenue(start_date=start_date, end_date=end_date)
        
        return {"data": {"revenue": revenue}}


class GetTopSearchesQuery(CommandQuery, AnalyticsQueryMixin):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = AnalyticsService()
        start_date, end_date = self._get_date_range(params)
        limit = params.get("limit", 10)
        
        searches = await service.get_top_searches(
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        return {"data": searches}


class GetTopProductsQuery(CommandQuery, AnalyticsQueryMixin):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = AnalyticsService()
        start_date, end_date = self._get_date_range(params)
        metric = params.get("metric", "views")
        limit = params.get("limit", 10)
        
        products = await service.get_top_products(
            metric=metric,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        return {"data": products}


class GetAnalyticsOverviewQuery(CommandQuery, AnalyticsQueryMixin):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get comprehensive analytics overview"""
        service = AnalyticsService()
        start_date, end_date = self._get_date_range(params)
        
        # Get multiple metrics in parallel
        unique_users = await service.get_unique_users(start_date=start_date, end_date=end_date)
        revenue = await service.get_revenue(start_date=start_date, end_date=end_date)
        orders = await service.get_event_count("order_placed", start_date=start_date, end_date=end_date)
        product_views = await service.get_event_count("product_view", start_date=start_date, end_date=end_date)
        searches = await service.get_event_count("search", start_date=start_date, end_date=end_date)
        cart_adds = await service.get_event_count("add_to_cart", start_date=start_date, end_date=end_date)
        
        top_searches = await service.get_top_searches(start_date=start_date, end_date=end_date, limit=5)
        top_products = await service.get_top_products("views", start_date=start_date, end_date=end_date, limit=5)
        
        return {
            "data": {
                "unique_users": unique_users,
                "revenue": revenue,
                "orders": orders,
                "product_views": product_views,
                "searches": searches,
                "cart_adds": cart_adds,
                "top_searches": top_searches,
                "top_products": top_products,
                "conversion_rate": (orders / product_views * 100) if product_views > 0 else 0,
                "cart_abandonment_rate": ((cart_adds - orders) / cart_adds * 100) if cart_adds > 0 else 0,
            }
        }
