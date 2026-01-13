from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from src.database.connection import db
from src.database.redis_connection import redis_client
from src.models.analytics import AnalyticsEvent, AnalyticsEventCreate, AnalyticsMetric, AnalyticsMetricCreate
from src.plugins.logger import logger
import json


class AnalyticsService:
    COLLECTION_NAME = "analytics_events"
    METRICS_COLLECTION = "analytics_metrics"
    
    # Redis key prefixes
    REDIS_PREFIX_EVENT = "analytics:event:"
    REDIS_PREFIX_METRIC = "analytics:metric:"
    REDIS_PREFIX_HLL = "analytics:hll:"
    REDIS_PREFIX_COUNTER = "analytics:counter:"
    REDIS_PREFIX_SET = "analytics:set:"
    
    # 24 hours in seconds
    REDIS_TTL_24H = 86400
    
    async def track_event(self, event_data: AnalyticsEventCreate) -> AnalyticsEvent:
        """Track an analytics event - stores in both Redis (24h) and MongoDB (persistent)"""
        redis = await redis_client.get_client()
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        # Prepare event
        event_dict = event_data.model_dump()
        if not event_dict.get("timestamp"):
            event_dict["timestamp"] = datetime.now(timezone.utc)
        else:
            if isinstance(event_dict["timestamp"], str):
                dt = datetime.fromisoformat(event_dict["timestamp"].replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                event_dict["timestamp"] = dt
        
        # Store in MongoDB (persistent)
        result = await collection.insert_one(event_dict)
        event_dict["_id"] = result.inserted_id
        event = AnalyticsEvent(**event_dict)
        
        # Store in Redis with 24h TTL
        event_key = f"{self.REDIS_PREFIX_EVENT}{event.id}"
        await redis.setex(
            event_key,
            self.REDIS_TTL_24H,
            json.dumps(event_dict, default=str)
        )
        
        # Update counters and sets in Redis
        await self._update_redis_metrics(event_data)
        
        logger.info(f"Analytics event tracked: {event_data.event_type} - {event.id}")
        return event
    
    async def _update_redis_metrics(self, event_data: AnalyticsEventCreate):
        """Update Redis metrics (HLL, counters, sets) for real-time analytics"""
        redis = await redis_client.get_client()
        timestamp = event_data.timestamp or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        date_str = timestamp.strftime("%Y-%m-%d")
        hour_str = timestamp.strftime("%Y-%m-%d-%H")
        
        event_type = event_data.event_type
        
        # Update daily counters
        daily_counter_key = f"{self.REDIS_PREFIX_COUNTER}{event_type}:{date_str}"
        await redis.incr(daily_counter_key)
        await redis.expire(daily_counter_key, self.REDIS_TTL_24H)
        
        # Update hourly counters
        hourly_counter_key = f"{self.REDIS_PREFIX_COUNTER}{event_type}:{hour_str}"
        await redis.incr(hourly_counter_key)
        await redis.expire(hourly_counter_key, self.REDIS_TTL_24H)
        
        # Update HyperLogLog for unique users
        if event_data.user_id:
            hll_key = f"{self.REDIS_PREFIX_HLL}users:{date_str}"
            await redis.pfadd(hll_key, str(event_data.user_id))
            await redis.expire(hll_key, self.REDIS_TTL_24H)
        
        # Update session tracking
        if event_data.session_id:
            session_key = f"{self.REDIS_PREFIX_SET}sessions:{date_str}"
            await redis.sadd(session_key, str(event_data.session_id))
            await redis.expire(session_key, self.REDIS_TTL_24H)
        
        # Event-specific metrics
        metadata = event_data.metadata or {}
        
        if event_type == "product_view" and metadata.get("product_id"):
            product_hll = f"{self.REDIS_PREFIX_HLL}product_views:{date_str}"
            await redis.pfadd(product_hll, str(metadata["product_id"]))
            await redis.expire(product_hll, self.REDIS_TTL_24H)
        
        if event_type == "search" and metadata.get("query"):
            search_key = f"{self.REDIS_PREFIX_COUNTER}search:{metadata['query']}:{date_str}"
            await redis.incr(search_key)
            await redis.expire(search_key, self.REDIS_TTL_24H)
        
        if event_type == "add_to_cart" and metadata.get("product_id"):
            cart_key = f"{self.REDIS_PREFIX_COUNTER}cart_adds:{metadata['product_id']}:{date_str}"
            await redis.incr(cart_key)
            await redis.expire(cart_key, self.REDIS_TTL_24H)
        
        if event_type == "order_placed":
            revenue_key = f"{self.REDIS_PREFIX_COUNTER}revenue:{date_str}"
            amount = metadata.get("amount", 0)
            await redis.incrbyfloat(revenue_key, float(amount))
            await redis.expire(revenue_key, self.REDIS_TTL_24H)
    
    async def track_metric(self, metric_data: AnalyticsMetricCreate) -> AnalyticsMetric:
        """Track a metric - stores in both Redis and MongoDB"""
        redis = await redis_client.get_client()
        database = await db.get_database()
        collection = database[self.METRICS_COLLECTION]
        
        metric_dict = metric_data.model_dump()
        if not metric_dict.get("timestamp"):
            metric_dict["timestamp"] = datetime.now(timezone.utc)
        
        # Store in MongoDB
        result = await collection.insert_one(metric_dict)
        metric_dict["_id"] = result.inserted_id
        metric = AnalyticsMetric(**metric_dict)
        
        # Store in Redis
        metric_key = f"{self.REDIS_PREFIX_METRIC}{metric.metric_name}:{metric_dict['timestamp'].strftime('%Y-%m-%d')}"
        await redis.setex(
            metric_key,
            self.REDIS_TTL_24H,
            json.dumps(metric_dict, default=str)
        )
        
        return metric
    
    async def get_events(
        self,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
        skip: int = 0
    ) -> List[AnalyticsEvent]:
        """Get events - checks Redis first (24h), then MongoDB (historical)"""
        now = datetime.now(timezone.utc)
        if start_date and start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date and end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        is_recent = start_date and (now - start_date).total_seconds() < self.REDIS_TTL_24H
        
        events = []
        
        # Try Redis for recent data (last 24h)
        if is_recent or (not start_date and not end_date):
            redis = await redis_client.get_client()
            # Get from Redis if within 24h window
            if not start_date or (now - start_date).total_seconds() < self.REDIS_TTL_24H:
                # Redis lookup would require scanning keys, so we'll use MongoDB for queries
                # Redis is better for real-time counters/metrics
                pass
        
        # Get from MongoDB (source of truth for queries)
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {}
        if event_type:
            query["event_type"] = event_type
        if user_id:
            query["user_id"] = user_id
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = start_date
            if end_date:
                query["timestamp"]["$lte"] = end_date
        
        cursor = collection.find(query).sort("timestamp", -1).skip(skip).limit(limit)
        async for doc in cursor:
            events.append(AnalyticsEvent(**doc))
        
        return events
    
    async def get_unique_users(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """Get unique users count - uses Redis HLL for recent, MongoDB for historical"""
        now = datetime.now(timezone.utc)
        if start_date and start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date and end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        
        # Use Redis HLL for last 24h
        if not start_date or (now - start_date).total_seconds() < self.REDIS_TTL_24H:
            redis = await redis_client.get_client()
            if start_date:
                date_str = start_date.strftime("%Y-%m-%d")
            else:
                date_str = now.strftime("%Y-%m-%d")
            
            hll_key = f"{self.REDIS_PREFIX_HLL}users:{date_str}"
            count = await redis.pfcount(hll_key)
            if count > 0:
                return count
        
        # Fallback to MongoDB for historical data
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {}
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = start_date
            if end_date:
                query["timestamp"]["$lte"] = end_date
        
        pipeline = [
            {"$match": query},
            {"$group": {"_id": "$user_id"}},
            {"$count": "unique_users"}
        ]
        
        result = await collection.aggregate(pipeline).to_list(length=1)
        return result[0]["unique_users"] if result else 0
    
    async def get_event_count(
        self,
        event_type: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """Get event count - uses Redis counter for recent, MongoDB for historical"""
        now = datetime.now(timezone.utc)
        if start_date and start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date and end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        
        # Use Redis counter for last 24h
        if not start_date or (now - start_date).total_seconds() < self.REDIS_TTL_24H:
            redis = await redis_client.get_client()
            if start_date:
                date_str = start_date.strftime("%Y-%m-%d")
            else:
                date_str = now.strftime("%Y-%m-%d")
            
            counter_key = f"{self.REDIS_PREFIX_COUNTER}{event_type}:{date_str}"
            count = await redis.get(counter_key)
            if count:
                return int(count)
        
        # Fallback to MongoDB
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {"event_type": event_type}
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = start_date
            if end_date:
                query["timestamp"]["$lte"] = end_date
        
        return await collection.count_documents(query)
    
    async def get_revenue(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> float:
        """Get total revenue - uses Redis for recent, MongoDB for historical"""
        now = datetime.now(timezone.utc)
        if start_date and start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date and end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        
        # Use Redis for last 24h
        if not start_date or (now - start_date).total_seconds() < self.REDIS_TTL_24H:
            redis = await redis_client.get_client()
            if start_date:
                date_str = start_date.strftime("%Y-%m-%d")
            else:
                date_str = now.strftime("%Y-%m-%d")
            
            revenue_key = f"{self.REDIS_PREFIX_COUNTER}revenue:{date_str}"
            revenue = await redis.get(revenue_key)
            if revenue:
                return float(revenue)
        
        # Fallback to MongoDB
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {
            "event_type": "order_placed"
        }
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = start_date
            if end_date:
                query["timestamp"]["$lte"] = end_date
        
        pipeline = [
            {"$match": query},
            {"$group": {
                "_id": None,
                "total_revenue": {"$sum": "$metadata.amount"}
            }}
        ]
        
        result = await collection.aggregate(pipeline).to_list(length=1)
        return result[0]["total_revenue"] if result and result[0].get("total_revenue") else 0.0
    
    async def get_top_searches(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top search queries"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query: Dict[str, Any] = {"event_type": "search"}
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = start_date
            if end_date:
                query["timestamp"]["$lte"] = end_date
        
        pipeline = [
            {"$match": query},
            {"$group": {
                "_id": "$metadata.query",
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}},
            {"$limit": limit},
            {"$project": {
                "query": "$_id",
                "count": 1,
                "_id": 0
            }}
        ]
        
        result = await collection.aggregate(pipeline).to_list(length=limit)
        return result
    
    async def get_top_products(
        self,
        metric: str = "views",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top products by views, cart adds, or purchases"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        event_type_map = {
            "views": "product_view",
            "cart_adds": "add_to_cart",
            "purchases": "order_placed"
        }
        
        event_type = event_type_map.get(metric, "product_view")
        
        query: Dict[str, Any] = {"event_type": event_type}
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = start_date
            if end_date:
                query["timestamp"]["$lte"] = end_date
        
        pipeline = [
            {"$match": query},
            {"$group": {
                "_id": "$metadata.product_id",
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}},
            {"$limit": limit},
            {"$project": {
                "product_id": "$_id",
                "count": 1,
                "_id": 0
            }}
        ]
        
        result = await collection.aggregate(pipeline).to_list(length=limit)
        return result
