import razorpay
import hmac
import hashlib
from typing import Dict, Any
from src.config import settings
from src.plugins.logger import logger


class RazorpayService:
    def __init__(self):
        self.client = razorpay.Client(
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
        )
    
    def create_order(self, amount: float, currency: str = "INR", notes: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create a Razorpay order"""
        try:
            order_data = {
                "amount": int(amount * 100),
                "currency": currency,
                "notes": notes or {}
            }
            order = self.client.order.create(data=order_data)
            logger.info(f"Razorpay order created: {order['id']}")
            return order
        except Exception as e:
            logger.error(f"Failed to create Razorpay order: {e}")
            raise ValueError(f"Failed to create payment order: {str(e)}")
    
    def verify_payment_signature(self, razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> bool:
        """Verify Razorpay payment signature using HMAC"""
        try:
            message = f"{razorpay_order_id}|{razorpay_payment_id}"
            generated_signature = hmac.new(
                settings.razorpay_key_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            is_valid = hmac.compare_digest(generated_signature, razorpay_signature)
            if not is_valid:
                logger.warning(f"Invalid payment signature for order {razorpay_order_id}")
            return is_valid
        except Exception as e:
            logger.error(f"Error verifying payment signature: {e}")
            return False
    
    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """Verify Razorpay webhook signature"""
        try:
            generated_signature = hmac.new(
                settings.razorpay_key_secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            is_valid = hmac.compare_digest(generated_signature, signature)
            if not is_valid:
                logger.warning("Invalid webhook signature")
            return is_valid
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False
