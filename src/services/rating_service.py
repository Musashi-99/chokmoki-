from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
from src.database.connection import db
from src.models.rating import Rating, RatingCreate
from src.models.order import Order
from src.plugins.logger import logger


class RatingService:
    COLLECTION_NAME = "ratings"
    
    async def create(self, rating_data: RatingCreate) -> Rating:
        """Create a rating after validating order is delivered"""
        database = await db.get_database()
        ratings_collection = database[self.COLLECTION_NAME]
        orders_collection = database["orders"]
        
        # Verify order exists and is delivered
        order = await orders_collection.find_one({"order_id": rating_data.order_id})
        if not order:
            raise ValueError("Order not found")
        
        # Check if order status is delivered
        order_status = order.get("status", {})
        if order_status.get("type") != "delivered":
            raise ValueError("Rating can only be submitted for delivered orders")
        
        # Verify user email matches order
        if order.get("user_email") != rating_data.email:
            raise ValueError("Order does not belong to this user")
        
        # Check if order contains the product
        items = order.get("items", [])
        product_found = any(
            item.get("product_id") == rating_data.product_id 
            for item in items
        )
        if not product_found:
            raise ValueError("Product not found in this order")
        
        # Check if user already rated this product for this order
        existing_rating = await ratings_collection.find_one({
            "order_id": rating_data.order_id,
            "product_id": rating_data.product_id,
            "user_email": rating_data.email
        })
        if existing_rating:
            raise ValueError("You have already rated this product for this order")
        
        # Create rating
        rating_dict = {
            "order_id": rating_data.order_id,
            "product_id": rating_data.product_id,
            "user_email": rating_data.email,
            "rating": rating_data.rating,
            "comment": rating_data.comment,
            "created_at": datetime.utcnow()
        }
        
        result = await ratings_collection.insert_one(rating_dict)
        rating_dict["_id"] = result.inserted_id
        
        rating = Rating(**rating_dict)
        return rating
    
    async def get_by_product(
        self, 
        product_id: str, 
        skip: int = 0, 
        limit: int = 20
    ) -> tuple[List[Rating], int]:
        """Get paginated ratings for a product, latest first"""
        database = await db.get_database()
        ratings_collection = database[self.COLLECTION_NAME]
        
        # Count total
        total = await ratings_collection.count_documents({"product_id": product_id})
        
        # Get paginated ratings, latest first
        cursor = ratings_collection.find({"product_id": product_id}).sort("created_at", -1).skip(skip).limit(limit)
        ratings = []
        async for doc in cursor:
            ratings.append(Rating(**doc))
        
        return ratings, total
    
    async def get_summary(self, product_id: str) -> Dict[str, Any]:
        """Get rating summary (count by star rating) for a product"""
        database = await db.get_database()
        ratings_collection = database[self.COLLECTION_NAME]
        
        # Aggregate ratings by star count
        pipeline = [
            {"$match": {"product_id": product_id}},
            {
                "$group": {
                    "_id": "$rating",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        star_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        async for doc in ratings_collection.aggregate(pipeline):
            star = int(doc["_id"])
            if 1 <= star <= 5:
                star_counts[star] = doc["count"]
        
        # Calculate average
        total_ratings = sum(star_counts.values())
        if total_ratings > 0:
            weighted_sum = sum(star * count for star, count in star_counts.items())
            average = weighted_sum / total_ratings
        else:
            average = 0.0
        
        return {
            "average": average,
            "total": total_ratings,
            "by_star": star_counts
        }
    
    async def check_user_can_rate(
        self, 
        order_id: str, 
        product_id: str, 
        user_email: str
    ) -> bool:
        """Check if user can rate a product from a specific order"""
        database = await db.get_database()
        ratings_collection = database[self.COLLECTION_NAME]
        orders_collection = database["orders"]
        
        # Check if order exists and is delivered
        order = await orders_collection.find_one({"order_id": order_id})
        if not order:
            return False
        
        order_status = order.get("status", {})
        if order_status.get("type") != "delivered":
            return False
        
        # Check if user email matches
        if order.get("user_email") != user_email:
            return False
        
        # Check if product is in order
        items = order.get("items", [])
        product_found = any(
            item.get("product_id") == product_id 
            for item in items
        )
        if not product_found:
            return False
        
        # Check if already rated
        existing_rating = await ratings_collection.find_one({
            "order_id": order_id,
            "product_id": product_id,
            "user_email": user_email
        })
        if existing_rating:
            return False
        
        return True
