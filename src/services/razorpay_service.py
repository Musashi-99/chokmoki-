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

    def fetch_payments_window(self, from_ts: int, to_ts: int, max_pages: int = 50) -> dict:
        """Bulk-fetch every captured/authorized payment in [from_ts, to_ts]
        (UNIX seconds) via GET /v1/payments, paginating count=100 at a time.

        Used by PaymentReconciliationService instead of one GET /v1/payments
        call per pending order — at any real volume, the number of pending
        (not-yet-webhooked) orders is a tiny fraction of total payment volume,
        so asking Razorpay once per pending order wastes API calls (and eats
        into Razorpay's own rate limit) for no benefit over asking once for
        "everything in this window" and matching locally.

        Returns {"payments": {razorpay_order_id: {id, status, amount_inr}},
        "pages_fetched": N, "raw_payments_seen": N, "hit_page_cap": bool} —
        the payments dict only includes entries that have an order_id and a
        captured/authorized status (entries without payment_capture, e.g.
        failed attempts, are dropped since reconciliation only cares about
        payments it needs to recover); the metadata is for the reconciliation
        run's own metrics/consistency reporting, so "what the API actually
        returned" is visible, not just "what we did with it."

        max_pages caps pagination at 50 * 100 = 5000 payments per run as a
        safety backstop against a runaway loop if Razorpay ever returned a
        malformed "full page" indefinitely — logged loudly if hit, since
        silently truncating here would silently drop recoverable orders.
        """
        payments: dict = {}
        skip = 0
        page_count = 0
        raw_payments_seen = 0
        hit_page_cap = False
        while True:
            page_count += 1
            if page_count > max_pages:
                hit_page_cap = True
                logger.error(
                    f"fetch_payments_window: hit max_pages={max_pages} cap "
                    f"(from={from_ts} to={to_ts}) — window may have more "
                    f"payments than were fetched; consider narrowing the window "
                    f"or raising max_pages."
                )
                break
            response = self.client.payment.all(
                data={"from": from_ts, "to": to_ts, "count": 100, "skip": skip}
            )
            items = response.get("items", [])
            raw_payments_seen += len(items)
            for payment in items:
                order_id = payment.get("order_id")
                if not order_id:
                    continue
                if payment.get("status") not in ("captured", "authorized"):
                    continue
                payments[order_id] = {
                    "id": payment.get("id"),
                    "status": payment.get("status"),
                    "amount_inr": int(payment.get("amount") or 0) / 100.0,
                }
            if len(items) < 100:
                break
            skip += 100
        return {
            "payments": payments,
            "pages_fetched": page_count if not hit_page_cap else max_pages,
            "raw_payments_seen": raw_payments_seen,
            "hit_page_cap": hit_page_cap,
        }

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
