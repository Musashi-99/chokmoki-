import razorpay
import razorpay.errors
import hmac
import hashlib
from typing import Optional
from src.config import settings
from src.plugins.logger import logger
from src.models.dto import RazorpayOrderResponseDTO


class RazorpayService:
    def __init__(self):
        self.client = razorpay.Client(
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
        )
    
    def create_order(self, amount: float, currency: str = "INR", notes: Optional[dict] = None) -> RazorpayOrderResponseDTO:
        """Create a Razorpay order"""
        try:
            order_data = {
                "amount": int(amount * 100),
                "currency": currency,
                "notes": notes or {},
                # Explicit auto-capture — without this, whether a successful
                # payment ever becomes "captured" (vs. sitting "authorized"
                # forever, requiring a separate manual capture call) depends
                # on the account's dashboard default, which we don't control
                # or want to depend on. Confirmed live: a real payment
                # authorized but never auto-captured, and the order only
                # completed via the client-side verify() fast path instead
                # of the webhook — the webhook (our source of truth) never
                # fired a completing event for it at all.
                "payment_capture": 1,
            }
            order_dict = self.client.order.create(data=order_data)
            logger.info(f"Razorpay order created: {order_dict['id']}")
            return RazorpayOrderResponseDTO(**order_dict)
        except Exception as e:
            logger.error(f"Failed to create Razorpay order: {e}")
            raise ValueError(f"Failed to create payment order: {str(e)}")
    
    def fetch_payment_amount_inr(self, razorpay_payment_id: str) -> float:
        """Return captured payment amount in INR (not paise)."""
        payment = self.client.payment.fetch(razorpay_payment_id)
        amount_paise = int(payment.get("amount") or 0)
        return amount_paise / 100.0

    def fetch_captured_payment(self, razorpay_order_id: str) -> Optional[dict]:
        """Return the captured/authorized payment for a Razorpay order, if any.

        Used by the F-13 reconciliation job to recover paid orders whose webhook
        was lost or never verified (e.g. RAZORPAY_WEBHOOK_SECRET was unset). We
        ask Razorpay directly for the authoritative payment state rather than
        trusting any client input. Returns a dict with `id`, `status`, and
        `amount_inr`, or ``None`` if no payment has been captured/authorized.
        """
        try:
            response = self.client.order.payments(razorpay_order_id)
            for payment in response.get("items", []):
                if payment.get("status") in ("captured", "authorized"):
                    return {
                        "id": payment.get("id"),
                        "status": payment.get("status"),
                        "amount_inr": int(payment.get("amount") or 0) / 100.0,
                    }
            return None
        except Exception as e:
            logger.error(
                f"Failed to fetch payments for Razorpay order {razorpay_order_id}: {e}"
            )
            return None

    def verify_payment_amount(
        self,
        razorpay_payment_id: str,
        expected_amount_inr: float,
        tolerance_paise: int = 1,
    ) -> bool:
        """Verify Razorpay captured amount matches the expected order total."""
        try:
            payment = self.client.payment.fetch(razorpay_payment_id)
            captured_paise = int(payment.get("amount") or 0)
            expected_paise = int(round(expected_amount_inr * 100))
            if abs(captured_paise - expected_paise) > tolerance_paise:
                logger.warning(
                    "Payment amount mismatch: expected %s paise, got %s paise",
                    expected_paise,
                    captured_paise,
                )
                return False
            status = payment.get("status")
            if status not in ("captured", "authorized"):
                logger.warning("Payment %s has unexpected status: %s", razorpay_payment_id, status)
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to verify payment amount: {e}")
            return False

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
        """Verify Razorpay webhook signature using Razorpay utility
        
        Note: If a webhook secret is set in Razorpay Dashboard, you MUST use that secret.
        The API secret will NOT work if a webhook secret is configured in the dashboard.
        """
        try:
            if not settings.razorpay_webhook_secret:
                logger.error(
                    "RAZORPAY_WEBHOOK_SECRET is not configured. "
                    "If you set a webhook secret in Razorpay Dashboard, you MUST set RAZORPAY_WEBHOOK_SECRET "
                    "in your environment variables. Webhook verification will fail without it."
                )
                return False
            
            self.client.utility.verify_webhook_signature(payload, signature, settings.razorpay_webhook_secret)
            logger.debug("Webhook signature verified successfully")
            return True
        except razorpay.errors.SignatureVerificationError as e:
            logger.warning(f"Invalid webhook signature: {str(e)}")
            logger.debug(f"Payload length: {len(payload)}, Signature prefix: {signature[:20] if signature else 'None'}...")
            logger.debug(f"Using webhook secret: {'Set' if settings.razorpay_webhook_secret else 'Not set'}")
            return False
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False
