from typing import List, Optional, Dict
import json
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
from src.config import settings
from src.database.redis_connection import redis_client
from src.plugins.logger import logger
from src.models.telegram import (
    OrderSnapshotDTO,
    AggregatedOrdersDTO,
    ProductAggregateDTO,
    NotificationResultDTO
)


class TelegramService:
    
    def is_enabled(self) -> bool:
        """Check if Telegram plugin is enabled"""
        if not settings.telegram_enabled:
            return False
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            return False
        return True
    
    async def push_order_to_queue(self, order_data: dict) -> None:
        """Push minimal order snapshot to Redis queue (non-blocking)"""
        if not self.is_enabled():
            return
        
        try:
            redis = await redis_client.get_client()
            
            # Extract minimal order info for each item
            order_id = order_data.get("order_id")
            items = order_data.get("items", [])
            created_at = order_data.get("created_at")
            
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()
            elif isinstance(created_at, str):
                pass
            else:
                created_at = datetime.utcnow().isoformat()
            
            # Push each item as separate entry for better aggregation
            for item in items:
                snapshot = OrderSnapshotDTO(
                    order_id=order_id,
                    product_id=item.get("product_id", ""),
                    product_name=item.get("product_name", ""),
                    quantity=item.get("quantity", 1),
                    price=item.get("unit_price", 0.0),
                    total=item.get("total_price", 0.0),
                    currency="INR",
                    created_at=created_at
                )
                
                await redis.lpush(settings.telegram_redis_key, snapshot.model_dump_json())
            
        except Exception as e:
            # Silently fail - don't affect order processing
            if logger:
                logger.warning(f"Failed to push order to Telegram queue: {e}")
    
    async def get_pending_orders(self) -> List[OrderSnapshotDTO]:
        """Get all pending orders from Redis"""
        if not self.is_enabled():
            return []
        
        try:
            redis = await redis_client.get_client()
            orders_json = await redis.lrange(settings.telegram_redis_key, 0, -1)
            
            orders = []
            for order_json in orders_json:
                try:
                    orders.append(OrderSnapshotDTO.model_validate_json(order_json))
                except (json.JSONDecodeError, ValueError):
                    continue
            
            return orders
        except Exception as e:
            if logger:
                logger.error(f"Failed to get pending orders from Redis: {e}")
            return []
    
    async def clear_pending_orders(self) -> None:
        """Clear all pending orders from Redis"""
        try:
            redis = await redis_client.get_client()
            await redis.delete(settings.telegram_redis_key)
        except Exception as e:
            if logger:
                logger.error(f"Failed to clear pending orders: {e}")
    
    def _aggregate_orders(self, orders: List[OrderSnapshotDTO]) -> AggregatedOrdersDTO:
        """Aggregate orders into summary"""
        if not orders:
            return AggregatedOrdersDTO()
        
        # Get unique order IDs
        unique_order_ids = set(order.order_id for order in orders)
        total_orders = len(unique_order_ids)
        
        # Calculate total revenue
        total_revenue = sum(order.total for order in orders)
        
        # Aggregate products
        products: Dict[str, ProductAggregateDTO] = {}
        for order in orders:
            if order.product_id not in products:
                products[order.product_id] = ProductAggregateDTO(
                    name=order.product_name,
                    quantity=0,
                    total_revenue=0.0
                )
            
            products[order.product_id].quantity += order.quantity
            products[order.product_id].total_revenue += order.total
        
        return AggregatedOrdersDTO(
            total_orders=total_orders,
            total_revenue=total_revenue,
            products=products
        )
    
    def _format_message(self, aggregated: AggregatedOrdersDTO, time_window: Optional[str] = None) -> str:
        """Format aggregated data into Telegram message"""
        # Header
        message = "🛒 New Orders Summary (Last 1 Hour)\n\n"
        message += f"📦 Total Orders: {aggregated.total_orders}\n"
        message += f"💰 Total Revenue: ₹{aggregated.total_revenue:,.0f}\n\n"
        
        # Products section
        if aggregated.products:
            message += "Products Ordered:\n\n"
            
            for idx, (product_id, product_data) in enumerate(aggregated.products.items(), 1):
                emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"][(idx - 1) % 10]
                product_url = f"{settings.telegram_product_base_url}/{product_id}"
                
                message += f"{emoji} {product_data.name} (x{product_data.quantity})\n"
                message += f"🔗 {product_url}\n"
                message += f"💵 ₹{product_data.total_revenue:,.0f}\n\n"
        
        # Footer
        if time_window:
            message += f"⏰ Time Window: {time_window}"
        else:
            now = datetime.utcnow()
            message += f"⏰ Generated at: {now.strftime('%H:%M')} UTC"
        
        return message
    
    def _split_message(self, message: str, max_chars: int = None) -> List[str]:
        """Split message if it exceeds Telegram limit"""
        if max_chars is None:
            max_chars = settings.telegram_message_max_chars
        
        if len(message) <= max_chars:
            return [message]
        
        messages = []
        lines = message.split("\n")
        current_message = ""
        
        for line in lines:
            # If adding this line would exceed limit, start new message
            if current_message and len(current_message) + len(line) + 1 > max_chars:
                messages.append(current_message.strip())
                current_message = line + "\n"
            else:
                current_message += line + "\n"
        
        if current_message.strip():
            messages.append(current_message.strip())
        
        return messages
    
    async def send_message(self, text: str) -> bool:
        """Send message to Telegram using python-telegram-bot SDK"""
        if not self.is_enabled():
            return False
        
        try:
            bot = Bot(token=settings.telegram_bot_token)
            await bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=text,
                parse_mode="Markdown",
                disable_web_page_preview=False
            )
            return True
        except TelegramError as e:
            if logger:
                logger.error(f"Telegram API error: {e}")
            return False
        except Exception as e:
            if logger:
                logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def process_and_send_notifications(self) -> NotificationResultDTO:
        """Main function to process pending orders and send notifications"""
        if not self.is_enabled():
            return NotificationResultDTO(
                success=False,
                message="Telegram plugin is not enabled",
                orders_processed=0
            )
        
        try:
            # Get pending orders
            orders = await self.get_pending_orders()
            
            if not orders:
                return NotificationResultDTO(
                    success=True,
                    message="No pending orders",
                    orders_processed=0
                )
            
            # Aggregate
            aggregated = self._aggregate_orders(orders)
            
            # Format message
            message = self._format_message(aggregated)
            
            # Split if needed
            messages = self._split_message(message)
            
            # Send messages sequentially
            all_sent = True
            for msg in messages:
                success = await self.send_message(msg)
                if not success:
                    all_sent = False
                    break
            
            # Clear Redis only if all messages sent successfully
            if all_sent:
                await self.clear_pending_orders()
                return NotificationResultDTO(
                    success=True,
                    message="Notifications sent successfully",
                    orders_processed=aggregated.total_orders,
                    messages_sent=len(messages)
                )
            else:
                # Don't clear if sending failed - allow retry
                return NotificationResultDTO(
                    success=False,
                    message="Failed to send some messages",
                    orders_processed=0
                )
                
        except Exception as e:
            if logger:
                logger.error(f"Failed to process Telegram notifications: {e}")
            return NotificationResultDTO(
                success=False,
                message=f"Error: {str(e)}",
                orders_processed=0
            )
