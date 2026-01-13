from typing import Optional, List
import json
from datetime import datetime, timedelta
from telegram import Bot
from telegram.error import TelegramError
from src.config import settings
from src.database.redis_connection import redis_client
from src.plugins.logger import logger
from src.models.telegram import (
    AggregatedStatsDTO,
    LastOrderedItemDTO,
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
        """Update aggregated stats in Redis (non-blocking)"""
        if not self.is_enabled():
            return
        
        try:
            redis = await redis_client.get_client()
            
            # Get current stats or create new
            stats_json = await redis.get(settings.telegram_redis_key)
            if stats_json:
                stats = AggregatedStatsDTO.model_validate_json(stats_json)
            else:
                stats = AggregatedStatsDTO()
            
            # Update stats with new order
            items = order_data.get("items", [])
            total_amount = order_data.get("total_amount", 0.0)
            
            stats.total_orders += 1
            stats.total_price += total_amount
            
            # Add items to total_items and update last_ordered_items
            for item in items:
                item_quantity = item.get("quantity", 1)
                item_name = item.get("product_name", "")
                stats.total_items += item_quantity
                
                # Add to last_ordered_items (keep only last 3)
                last_item = LastOrderedItemDTO(name=item_name, quantity=item_quantity)
                stats.last_ordered_items.insert(0, last_item)
                if len(stats.last_ordered_items) > 3:
                    stats.last_ordered_items = stats.last_ordered_items[:3]
            
            # Store updated stats with 24-hour expiration
            await redis.setex(
                settings.telegram_redis_key,
                86400,  # 24 hours in seconds
                stats.model_dump_json()
            )
            
        except Exception as e:
            # Silently fail - don't affect order processing
            if logger:
                logger.warning(f"Failed to update Telegram stats: {e}")
    
    async def get_aggregated_stats(self) -> Optional[AggregatedStatsDTO]:
        """Get aggregated stats from Redis"""
        if not self.is_enabled():
            return None
        
        try:
            redis = await redis_client.get_client()
            stats_json = await redis.get(settings.telegram_redis_key)
            
            if stats_json:
                return AggregatedStatsDTO.model_validate_json(stats_json)
            return None
        except Exception as e:
            if logger:
                logger.error(f"Failed to get aggregated stats from Redis: {e}")
            return None
    
    async def clear_aggregated_stats(self) -> None:
        """Clear aggregated stats from Redis"""
        try:
            redis = await redis_client.get_client()
            await redis.delete(settings.telegram_redis_key)
        except Exception as e:
            if logger:
                logger.error(f"Failed to clear aggregated stats: {e}")
    
    def _format_message(self, stats: AggregatedStatsDTO) -> str:
        """Format aggregated stats into Telegram message"""
        # Header
        message = "🛒 Orders Summary\n\n"
        message += f"📦 Total Orders: {stats.total_orders}\n"
        message += f"📊 Total Items: {stats.total_items}\n"
        message += f"💰 Total Revenue: ₹{stats.total_price:,.0f}\n\n"
        
        # Last ordered items section
        if stats.last_ordered_items:
            message += "Last Ordered Items:\n\n"
            
            for idx, item in enumerate(stats.last_ordered_items, 1):
                emoji = ["1️⃣", "2️⃣", "3️⃣"][idx - 1]
                message += f"{emoji} {item.name} (x{item.quantity})\n"
        
        # Footer
        now = datetime.utcnow()
        message += f"\n⏰ Generated at: {now.strftime('%H:%M')} UTC"
        
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
        """Main function to read aggregated stats and send notifications"""
        if not self.is_enabled():
            return NotificationResultDTO(
                success=False,
                message="Telegram plugin is not enabled",
                orders_processed=0
            )
        
        try:
            # Get aggregated stats
            stats = await self.get_aggregated_stats()
            
            if not stats or stats.total_orders == 0:
                return NotificationResultDTO(
                    success=True,
                    message="No orders to report",
                    orders_processed=0
                )
            
            # Format message
            message = self._format_message(stats)
            
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
                await self.clear_aggregated_stats()
                return NotificationResultDTO(
                    success=True,
                    message="Notifications sent successfully",
                    orders_processed=stats.total_orders,
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
