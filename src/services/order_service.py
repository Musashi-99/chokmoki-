from typing import List, Optional
from bson import ObjectId
from datetime import datetime
import uuid
import json
from src.database.connection import db
from src.database.redis_connection import redis_client
from src.models.order import Order, OrderCreateInput, ValidatedOrderItem, OrderStatus, ShippingAddressInOrder
from src.models.common import PricingDTO
from src.models.dto import OrderInitiateResponseDTO, OrderLogDTO
from src.models.product import Product
from src.services.product_service import ProductService
from src.services.razorpay_service import RazorpayService
from src.config import settings
from src.plugins.logger import logger

# Optional Telegram import
try:
    from src.services.telegram_service import TelegramService
except ImportError:
    TelegramService = None


class OrderService:
    COLLECTION_NAME = "orders"
    ORDER_LOGS_COLLECTION = "order_logs"

    async def ensure_indexes(self) -> None:
        """Unique order_id prevents duplicate inserts under concurrent webhooks."""
        database = await db.get_database()
        orders_collection = database[self.COLLECTION_NAME]
        logs_collection = database[self.ORDER_LOGS_COLLECTION]
        await orders_collection.create_index("order_id", unique=True)
        await logs_collection.create_index("order_id", unique=True)

    def _order_from_doc(self, order_doc: dict) -> Order:
        if isinstance(order_doc.get("shipping_address"), dict):
            order_doc = {**order_doc}
            order_doc["shipping_address"] = ShippingAddressInOrder(
                **order_doc["shipping_address"]
            )
        return Order(**order_doc)

    async def _clear_pending_redis(self, order_id: str) -> None:
        redis = await redis_client.get_client()
        await redis.delete(f"pending_order:{order_id}")

    async def complete_pending_order(
        self,
        order_id: str,
        razorpay_order_id: str,
        razorpay_payment_id: str,
    ) -> tuple[Optional[Order], str]:
        """
        Atomically persist a paid order from Redis to MongoDB.
        Returns (order, status) where status is 'created', 'existing', or 'not_found'.
        """
        database = await db.get_database()
        orders_collection = database[self.COLLECTION_NAME]
        logs_collection = database[self.ORDER_LOGS_COLLECTION]

        existing = await orders_collection.find_one({"order_id": order_id})
        if existing:
            await self._clear_pending_redis(order_id)
            return self._order_from_doc(existing), "existing"

        redis = await redis_client.get_client()
        redis_key = f"pending_order:{order_id}"
        order_json = await redis.get(redis_key)
        if not order_json:
            existing = await orders_collection.find_one({"order_id": order_id})
            if existing:
                return self._order_from_doc(existing), "existing"
            return None, "not_found"

        order_dict = json.loads(order_json)
        order_dict["payment_status"] = "completed"
        order_dict["razorpay_order_id"] = razorpay_order_id
        order_dict["razorpay_payment_id"] = razorpay_payment_id
        order_dict["created_at"] = datetime.fromisoformat(order_dict["created_at"])
        order_dict.pop("_id", None)

        result = await orders_collection.update_one(
            {"order_id": order_id},
            {"$setOnInsert": order_dict},
            upsert=True,
        )
        created = result.upserted_id is not None

        saved = await orders_collection.find_one({"order_id": order_id})
        if not saved:
            return None, "not_found"

        if created:
            log_dict = {
                "order_id": order_id,
                "raw_data": order_dict.get("raw_order_log", {}),
                "created_at": datetime.utcnow(),
            }
            await logs_collection.update_one(
                {"order_id": order_id},
                {"$setOnInsert": log_dict},
                upsert=True,
            )
            if TelegramService:
                telegram_service = TelegramService()
                try:
                    await telegram_service.push_order_to_queue(saved)
                except Exception as e:
                    logger.warning(f"Failed to push order to Telegram queue: {e}")

        await self._clear_pending_redis(order_id)
        status = "created" if created else "existing"
        if status == "created":
            logger.info(f"Order {order_id} moved from Redis to MongoDB")
        else:
            logger.info(f"Order {order_id} already in MongoDB (concurrent completion)")
        return self._order_from_doc(saved), status
    
    def _validate_variant(self, product: Product, variant: dict) -> bool:
        """Validate that the variant matches the product's variant structure"""
        if not product.product_variants:
            # If product has no variants, only accept default variant
            return variant == {"default": "default"}
        
        # Check each variant key-value pair
        for variant_name, variant_value in variant.items():
            # Find matching variant definition in product
            product_variant = next(
                (pv for pv in product.product_variants if pv.variant_name == variant_name),
                None
            )
            
            if not product_variant:
                logger.warning(f"Variant name '{variant_name}' not found in product {product.id}")
                return False
            
            # Check if variant value exists and is active
            variant_value_obj = next(
                (vv for vv in product_variant.variant_values if vv.label == variant_value),
                None
            )
            
            if not variant_value_obj or not variant_value_obj.active:
                logger.warning(f"Variant value '{variant_value}' for '{variant_name}' not found or inactive in product {product.id}")
                return False
        
        # Check that all required variant names are provided
        variant_names_in_product = {pv.variant_name for pv in product.product_variants}
        variant_names_provided = set(variant.keys())
        
        if variant_names_in_product != variant_names_provided:
            logger.warning(f"Variant names mismatch. Product has: {variant_names_in_product}, provided: {variant_names_provided}")
            return False
        
        return True
    
    def _recalculate_pricing(self, validated_items: List[ValidatedOrderItem]) -> PricingDTO:
        """Recalculate pricing from validated items - never trust user data"""
        subtotal = sum(item.total_price for item in validated_items)
        discount = 0.0  # Can be calculated based on business logic
        shipping = 0.0  # Can be calculated based on shipping address
        total = subtotal - discount + shipping
        
        return PricingDTO(
            subtotal=subtotal,
            discount=discount,
            shipping=shipping,
            total=total
        )
    
    async def create(self, order_data: OrderCreateInput) -> Order:
        """Create order with validation and recalculation (for COD)"""
        if order_data.paymentMethod == "razorpay":
            raise ValueError("Use initiate_order for razorpay payments")
        
        validated_items, pricing = await self._validate_and_prepare_order(order_data)
        
        database = await db.get_database()
        orders_collection = database[self.COLLECTION_NAME]
        logs_collection = database[self.ORDER_LOGS_COLLECTION]
        
        raw_order_log = order_data.model_dump()
        order_id = str(uuid.uuid4())
        raw_order_log["order_id"] = order_id
        raw_order_log["received_at"] = datetime.utcnow().isoformat()
        
        # Convert to dict for MongoDB
        order_dict = {
            "order_id": order_id,
            "user_email": order_data.userEmail,
            "shipping_address": order_data.shippingAddress.model_dump(),
            "items": [item.model_dump() for item in validated_items],
            "special_message": order_data.specialMessage or "",
            "subtotal": pricing.subtotal,
            "discount": pricing.discount,
            "shipping": pricing.shipping,
            "total_amount": pricing.total,
            "payment_method": order_data.paymentMethod or "cod",
            "payment_status": "completed" if order_data.paymentMethod == "cod" else None,
            "status": OrderStatus(type="accepted").model_dump(),
            "created_at": datetime.utcnow(),
            "raw_order_log": raw_order_log
        }
        
        result = await orders_collection.insert_one(order_dict)
        order_dict["_id"] = result.inserted_id
        
        # Convert log to dict for MongoDB
        log_dict = {
            "order_id": order_id,
            "raw_data": raw_order_log,
            "created_at": datetime.utcnow()
        }
        await logs_collection.insert_one(log_dict)
        
        # Push to Telegram queue (non-blocking, best-effort)
        if TelegramService:
            telegram_service = TelegramService()
            try:
                await telegram_service.push_order_to_queue(order_dict)
            except Exception as e:
                logger.warning(f"Failed to push COD order to Telegram queue: {e}")
        
        logger.info(f"Order created: {order_id} (MongoDB ID: {result.inserted_id})")
        # Convert shipping_address dict to DTO when creating Order
        order_dict["shipping_address"] = ShippingAddressInOrder(**order_dict["shipping_address"])
        return Order(**order_dict)
    
    async def get_by_id(self, order_id: str) -> Optional[Order]:
        """Get order by order_id (not MongoDB _id)"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        order_dict = await collection.find_one({"order_id": order_id})
        if order_dict:
            # Convert shipping_address dict to DTO
            if isinstance(order_dict.get("shipping_address"), dict):
                order_dict["shipping_address"] = ShippingAddressInOrder(**order_dict["shipping_address"])
            return Order(**order_dict)
        return None
    
    async def get_by_mongo_id(self, mongo_id: str) -> Optional[Order]:
        """Get order by MongoDB _id"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        order_dict = await collection.find_one({"_id": ObjectId(mongo_id)})
        if order_dict:
            # Convert shipping_address dict to DTO
            if isinstance(order_dict.get("shipping_address"), dict):
                order_dict["shipping_address"] = ShippingAddressInOrder(**order_dict["shipping_address"])
            return Order(**order_dict)
        return None
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 20,
        user_email: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        sort_order: int = -1,
    ) -> List[Order]:
        """List orders with optional filtering, search, and date range"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]

        query = self._build_order_query(user_email, status, search, from_date, to_date)
        cursor = collection.find(query).sort("created_at", sort_order).skip(skip).limit(limit)
        orders_dict = await cursor.to_list(length=limit)

        orders = []
        for order_dict in orders_dict:
            if isinstance(order_dict.get("shipping_address"), dict):
                order_dict["shipping_address"] = ShippingAddressInOrder(**order_dict["shipping_address"])
            orders.append(Order(**order_dict))

        return orders

    async def count(
        self,
        user_email: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> int:
        """Count orders matching the given filters"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]

        query = self._build_order_query(user_email, status, search, from_date, to_date)
        return await collection.count_documents(query)

    @staticmethod
    def _parse_filter_datetime(value: str, *, end_of_day: bool = False) -> datetime:
        """Parse YYYY-MM-DD (admin date inputs) or ISO datetimes for list filters."""
        raw = value.strip()
        if "T" in raw or raw.endswith("Z"):
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt
        day = datetime.fromisoformat(raw)
        if end_of_day:
            return day.replace(hour=23, minute=59, second=59, microsecond=999999)
        return day.replace(hour=0, minute=0, second=0, microsecond=0)

    def _build_order_query(
        self,
        user_email: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> dict:
        query: dict = {}
        if user_email:
            query["user_email"] = user_email
        if status:
            query["status.type"] = status
        if search:
            query["$or"] = [
                {"order_id": {"$regex": search, "$options": "i"}},
                {"user_email": {"$regex": search, "$options": "i"}},
                {"shipping_address.full_name": {"$regex": search, "$options": "i"}},
                {"shipping_address.phone": {"$regex": search, "$options": "i"}},
            ]
        if from_date or to_date:
            date_filter: dict = {}
            if from_date:
                date_filter["$gte"] = self._parse_filter_datetime(from_date, end_of_day=False)
            if to_date:
                date_filter["$lte"] = self._parse_filter_datetime(to_date, end_of_day=True)
            if date_filter:
                query["created_at"] = date_filter
        return query
    
    async def get_order_log(self, order_id: str) -> Optional[OrderLogDTO]:
        """Get raw order log for debugging"""
        database = await db.get_database()
        logs_collection = database[self.ORDER_LOGS_COLLECTION]
        
        log_dict = await logs_collection.find_one({"order_id": order_id})
        if log_dict:
            # Convert datetime to string if needed
            if isinstance(log_dict.get("created_at"), datetime):
                log_dict["created_at"] = log_dict["created_at"].isoformat()
            return OrderLogDTO(**log_dict)
        return None
    
    async def update_status(
        self,
        order_id: str,
        status: OrderStatus
    ) -> Optional[Order]:
        """Update order status by order_id"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        result = await collection.update_one(
            {"order_id": order_id},
            {"$set": {"status": status.model_dump()}}
        )
        
        if result.modified_count > 0:
            return await self.get_by_id(order_id)
        return None
    
    async def _validate_and_prepare_order(self, order_data: OrderCreateInput) -> tuple[List[ValidatedOrderItem], PricingDTO]:
        """Validate order items and recalculate pricing - shared logic"""
        product_service = ProductService()
        validated_items: List[ValidatedOrderItem] = []
        
        for item in order_data.items:
            product = await product_service.get_by_id(item.productId)
            if not product:
                raise ValueError(f"Product {item.productId} not found")
            if not product.active:
                raise ValueError(f"Product {item.productId} is not active")
            if not self._validate_variant(product, item.variant):
                raise ValueError(f"Invalid variant {item.variant} for product {item.productId}")
            
            unit_price = float(product.price_inr)
            total_price = unit_price * item.quantity
            
            validated_items.append(ValidatedOrderItem(
                product_id=item.productId,
                product_name=product.name,
                variant=item.variant,
                quantity=item.quantity,
                unit_price=unit_price,
                total_price=total_price,
                size=item.size
            ))
        
        pricing = self._recalculate_pricing(validated_items)
        return validated_items, pricing
    
    async def initiate_order(self, order_data: OrderCreateInput) -> OrderInitiateResponseDTO:
        """Initiate order: validate, store in Redis, create Razorpay order"""
        if order_data.paymentMethod != "razorpay":
            raise ValueError("initiate_order only supports razorpay payment method")
        
        validated_items, pricing = await self._validate_and_prepare_order(order_data)
        
        order_id = str(uuid.uuid4())
        raw_order_log = order_data.model_dump()
        raw_order_log["order_id"] = order_id
        raw_order_log["received_at"] = datetime.utcnow().isoformat()
        
        # Convert to dict for Redis storage
        order_dict = {
            "order_id": order_id,
            "user_email": order_data.userEmail,
            "shipping_address": order_data.shippingAddress.model_dump(),
            "items": [item.model_dump() for item in validated_items],
            "special_message": order_data.specialMessage or "",
            "subtotal": pricing.subtotal,
            "discount": pricing.discount,
            "shipping": pricing.shipping,
            "total_amount": pricing.total,
            "payment_method": "razorpay",
            "payment_status": "pending",
            "status": OrderStatus(type="accepted").model_dump(),
            "created_at": datetime.utcnow().isoformat(),
            "raw_order_log": raw_order_log
        }
        
        redis = await redis_client.get_client()
        redis_key = f"pending_order:{order_id}"
        await redis.setex(redis_key, 3600, json.dumps(order_dict, default=str))
        
        razorpay_service = RazorpayService()
        razorpay_order = razorpay_service.create_order(
            amount=pricing.total,
            notes={"order_id": order_id, "user_email": order_data.userEmail}
        )
        
        logger.info(f"Order initiated: {order_id}, Razorpay order: {razorpay_order.id}")
        
        return OrderInitiateResponseDTO(
            order_id=order_id,
            razorpay_order_id=razorpay_order.id,
            razorpay_key_id=settings.razorpay_key_id,
            amount=pricing.total
        )
    
    async def verify_payment(
        self,
        order_id: str,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str
    ) -> Order:
        """Verify payment signature and move order from Redis to MongoDB"""
        razorpay_service = RazorpayService()
        
        if not razorpay_service.verify_payment_signature(
            razorpay_order_id, razorpay_payment_id, razorpay_signature
        ):
            raise ValueError("Invalid payment signature")

        order, status = await self.complete_pending_order(
            order_id, razorpay_order_id, razorpay_payment_id
        )
        if status == "not_found":
            raise ValueError(f"Order {order_id} not found in Redis")
        return order
