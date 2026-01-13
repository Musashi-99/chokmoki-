from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
import uuid
import json
from src.database.connection import db
from src.database.redis_connection import redis_client
from src.models.order import Order, OrderCreateInput, ValidatedOrderItem, OrderStatus
from src.models.product import Product
from src.services.product_service import ProductService
from src.services.razorpay_service import RazorpayService
from src.config import settings
from src.plugins.logger import logger


class OrderService:
    COLLECTION_NAME = "orders"
    ORDER_LOGS_COLLECTION = "order_logs"
    
    def _validate_variant(self, product: Product, variant: Dict[str, str]) -> bool:
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
    
    def _recalculate_pricing(self, validated_items: List[ValidatedOrderItem]) -> Dict[str, float]:
        """Recalculate pricing from validated items - never trust user data"""
        subtotal = sum(item.total_price for item in validated_items)
        discount = 0.0  # Can be calculated based on business logic
        shipping = 0.0  # Can be calculated based on shipping address
        total = subtotal - discount + shipping
        
        return {
            "subtotal": subtotal,
            "discount": discount,
            "shipping": shipping,
            "total": total
        }
    
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
        
        order_dict = {
            "order_id": order_id,
            "user_email": order_data.userEmail,
            "shipping_address": order_data.shippingAddress.model_dump(),
            "items": [item.model_dump() for item in validated_items],
            "special_message": order_data.specialMessage or "",
            "subtotal": pricing["subtotal"],
            "discount": pricing["discount"],
            "shipping": pricing["shipping"],
            "total_amount": pricing["total"],
            "payment_method": order_data.paymentMethod or "cod",
            "payment_status": "completed" if order_data.paymentMethod == "cod" else None,
            "status": OrderStatus(type="accepted").model_dump(),
            "created_at": datetime.utcnow(),
            "raw_order_log": raw_order_log
        }
        
        result = await orders_collection.insert_one(order_dict)
        order_dict["_id"] = result.inserted_id
        
        await logs_collection.insert_one({
            "order_id": order_id,
            "raw_data": raw_order_log,
            "created_at": datetime.utcnow()
        })
        
        logger.info(f"Order created: {order_id} (MongoDB ID: {result.inserted_id})")
        return Order(**order_dict)
    
    async def get_by_id(self, order_id: str) -> Optional[Order]:
        """Get order by order_id (not MongoDB _id)"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        order = await collection.find_one({"order_id": order_id})
        if order:
            return Order(**order)
        return None
    
    async def get_by_mongo_id(self, mongo_id: str) -> Optional[Order]:
        """Get order by MongoDB _id"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        order = await collection.find_one({"_id": ObjectId(mongo_id)})
        if order:
            return Order(**order)
        return None
    
    async def list(self, skip: int = 0, limit: int = 20, user_email: Optional[str] = None) -> List[Order]:
        """List orders, optionally filtered by user email"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query = {}
        if user_email:
            query["user_email"] = user_email
        
        cursor = collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        orders = await cursor.to_list(length=limit)
        
        return [Order(**order) for order in orders]
    
    async def count(self, user_email: Optional[str] = None) -> int:
        """Count orders matching the given filters"""
        database = await db.get_database()
        collection = database[self.COLLECTION_NAME]
        
        query = {}
        if user_email:
            query["user_email"] = user_email
        
        return await collection.count_documents(query)
    
    async def get_order_log(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get raw order log for debugging"""
        database = await db.get_database()
        logs_collection = database[self.ORDER_LOGS_COLLECTION]
        
        log = await logs_collection.find_one({"order_id": order_id})
        return log
    
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
    
    async def _validate_and_prepare_order(self, order_data: OrderCreateInput) -> tuple[List[ValidatedOrderItem], Dict[str, float]]:
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
            
            unit_price = product.selling_price
            total_price = unit_price * item.quantity
            
            validated_items.append(ValidatedOrderItem(
                product_id=item.productId,
                product_name=product.name,
                variant=item.variant,
                quantity=item.quantity,
                unit_price=unit_price,
                total_price=total_price
            ))
        
        pricing = self._recalculate_pricing(validated_items)
        return validated_items, pricing
    
    async def initiate_order(self, order_data: OrderCreateInput) -> Dict[str, Any]:
        """Initiate order: validate, store in Redis, create Razorpay order"""
        if order_data.paymentMethod != "razorpay":
            raise ValueError("initiate_order only supports razorpay payment method")
        
        validated_items, pricing = await self._validate_and_prepare_order(order_data)
        
        order_id = str(uuid.uuid4())
        raw_order_log = order_data.model_dump()
        raw_order_log["order_id"] = order_id
        raw_order_log["received_at"] = datetime.utcnow().isoformat()
        
        order_dict = {
            "order_id": order_id,
            "user_email": order_data.userEmail,
            "shipping_address": order_data.shippingAddress.model_dump(),
            "items": [item.model_dump() for item in validated_items],
            "special_message": order_data.specialMessage or "",
            "subtotal": pricing["subtotal"],
            "discount": pricing["discount"],
            "shipping": pricing["shipping"],
            "total_amount": pricing["total"],
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
            amount=pricing["total"],
            notes={"order_id": order_id, "user_email": order_data.userEmail}
        )
        
        logger.info(f"Order initiated: {order_id}, Razorpay order: {razorpay_order['id']}")
        
        return {
            "order_id": order_id,
            "razorpay_order_id": razorpay_order["id"],
            "razorpay_key_id": settings.razorpay_key_id,
            "amount": pricing["total"]
        }
    
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
        
        database = await db.get_database()
        orders_collection = database[self.COLLECTION_NAME]
        
        existing_order = await orders_collection.find_one({"order_id": order_id})
        if existing_order:
            logger.info(f"Order {order_id} already exists in MongoDB, skipping duplicate processing")
            redis = await redis_client.get_client()
            redis_key = f"pending_order:{order_id}"
            await redis.delete(redis_key)
            return Order(**existing_order)
        
        redis = await redis_client.get_client()
        redis_key = f"pending_order:{order_id}"
        order_json = await redis.get(redis_key)
        
        if not order_json:
            raise ValueError(f"Order {order_id} not found in Redis")
        
        order_dict = json.loads(order_json)
        order_dict["payment_status"] = "completed"
        order_dict["razorpay_order_id"] = razorpay_order_id
        order_dict["razorpay_payment_id"] = razorpay_payment_id
        order_dict["created_at"] = datetime.fromisoformat(order_dict["created_at"])
        
        logs_collection = database[self.ORDER_LOGS_COLLECTION]
        
        try:
            result = await orders_collection.insert_one(order_dict)
            order_dict["_id"] = result.inserted_id
            
            await logs_collection.insert_one({
                "order_id": order_id,
                "raw_data": order_dict.get("raw_order_log", {}),
                "created_at": datetime.utcnow()
            })
            
            await redis.delete(redis_key)
            logger.info(f"Payment verified and order created: {order_id}")
            return Order(**order_dict)
        except Exception as e:
            logger.error(f"Failed to create order {order_id} in MongoDB: {e}")
            await redis.delete(redis_key)
            raise
