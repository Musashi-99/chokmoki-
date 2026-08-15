from __future__ import annotations

from typing import TYPE_CHECKING

from src.config import settings
from src.utils.money import money

if TYPE_CHECKING:
    from src.models.order import Order

BRAND_COLOR = "#0f0f0f"
ACCENT_COLOR = "#b8860b"  # muted gold, matches jewellery brand positioning

# Keys must exactly match Order.shipment_status literal values
# (src/models/order.py) — that field (not OrderStatus.type) is what
# ShiprocketService._apply_status_update actually publishes on every real
# transition. "pending" (the initial default) is intentionally omitted —
# it's never itself a transition, it's the starting state before the first
# one arrives.
SHIPMENT_STATUS_COPY = {
    "awb_assigned": ("Your order is being prepared for pickup", "A courier has been assigned to your order."),
    "pickup_scheduled": ("Pickup scheduled for your order", "Your courier pickup has been scheduled."),
    "picked_up": ("Your order has been picked up", "Your courier has picked up your order."),
    "in_transit": ("Your order is on its way", "Your order is currently in transit."),
    "out_for_delivery": ("Your order is out for delivery", "Your order will arrive today."),
    "delivered": ("Your order has been delivered", "Your order has been delivered. We hope you love it!"),
    "rto_initiated": ("Your order is being returned", "Your order is being returned to us."),
    "rto_delivered": ("Your returned order has arrived back with us", "Your returned order has arrived back with us."),
    "cancellation_requested": ("Your order cancellation is being processed", "We've received your cancellation request and are processing it."),
    "cancelled": ("Your order was cancelled", "Your order has been cancelled."),
    "failed": ("There's an issue with your delivery", "We ran into a delivery issue with your order — our team will be in touch."),
}


def _wrap(preheader: str, body_html: str) -> str:
    """Shared branded shell every outgoing email renders inside."""
    return f"""
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f5f3ef;font-family:Georgia,'Times New Roman',serif;">
    <span style="display:none;max-height:0;overflow:hidden;">{preheader}</span>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f3ef;padding:32px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;">
            <tr>
              <td style="background:{BRAND_COLOR};padding:28px 32px;text-align:center;">
                <div style="color:#ffffff;font-size:24px;letter-spacing:2px;">{settings.invoice_brand_name.upper()}</div>
                <div style="color:{ACCENT_COLOR};font-size:12px;letter-spacing:1px;margin-top:4px;">{settings.invoice_brand_tagline}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;color:#222222;font-size:15px;line-height:1.6;">
                {body_html}
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px;background:#faf9f6;color:#888888;font-size:12px;text-align:center;">
                {settings.invoice_brand_name} &middot; <a href="{settings.frontend_url}" style="color:{ACCENT_COLOR};">{settings.frontend_url.replace('https://', '').replace('http://', '')}</a>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""".strip()


def render_otp_email(otp: str, expiry_minutes: int) -> tuple[str, str]:
    subject = f"{otp} is your {settings.invoice_brand_name} verification code"
    body = f"""
    <p>Your one-time verification code is:</p>
    <p style="font-size:32px;letter-spacing:8px;font-weight:bold;color:{BRAND_COLOR};margin:24px 0;">{otp}</p>
    <p>This code expires in {expiry_minutes} minute{'s' if expiry_minutes != 1 else ''}. If you didn't request this, you can safely ignore this email.</p>
    """
    return subject, _wrap(f"Your verification code is {otp}", body)


def _order_items_rows(order: "Order") -> str:
    rows = []
    for item in order.items:
        variant = ", ".join(f"{k}: {v}" for k, v in (item.variant or {}).items())
        rows.append(
            f"""
            <tr>
              <td style="padding:8px 0;border-bottom:1px solid #eee;">
                {item.product_name}{f'<br/><span style="color:#888;font-size:12px;">{variant}</span>' if variant else ''}
              </td>
              <td style="padding:8px 0;border-bottom:1px solid #eee;text-align:center;">&times;{item.quantity}</td>
              <td style="padding:8px 0;border-bottom:1px solid #eee;text-align:right;">&#8377;{money(item.total_price):,.2f}</td>
            </tr>
            """
        )
    return "".join(rows)


def render_order_confirmation_email(order: "Order") -> tuple[str, str]:
    address = order.shipping_address
    subject = f"Order {order.order_id} confirmed — {settings.invoice_brand_name}"
    body = f"""
    <p>Hi {address.full_name},</p>
    <p>Thanks for your order! We've received it and it's being prepared.</p>
    <p style="margin:20px 0 8px;"><strong>Order #{order.order_id}</strong></p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:14px;">
      {_order_items_rows(order)}
      {f'''<tr>
        <td colspan="2" style="padding-top:8px;text-align:right;">Discount{f" ({order.applied_discount.code})" if getattr(order, "applied_discount", None) and getattr(order.applied_discount, "code", None) else ""}</td>
        <td style="padding-top:8px;text-align:right;">-&#8377;{money(order.discount):,.2f}</td>
      </tr>''' if money(getattr(order, "discount", 0) or 0) > 0 else ""}
      {f'''<tr>
        <td colspan="2" style="padding-top:8px;text-align:right;">Shipping</td>
        <td style="padding-top:8px;text-align:right;">&#8377;{money(order.shipping):,.2f}</td>
      </tr>''' if money(getattr(order, "shipping", 0) or 0) > 0 else ""}
      <tr>
        <td colspan="2" style="padding-top:12px;text-align:right;font-weight:bold;">Total</td>
        <td style="padding-top:12px;text-align:right;font-weight:bold;">&#8377;{money(order.total_amount):,.2f}</td>
      </tr>
    </table>
    <p style="margin-top:24px;"><strong>Shipping to</strong><br/>
      {address.full_name}<br/>
      {address.address_line1}{f', {address.address_line2}' if address.address_line2 else ''}<br/>
      {address.city}, {address.state} {address.postal_code}<br/>
      {address.country}
    </p>
    <p style="margin-top:24px;">
      <a href="{settings.frontend_url}/account" style="display:inline-block;background:{BRAND_COLOR};color:#ffffff;padding:12px 24px;text-decoration:none;border-radius:4px;">View your order</a>
    </p>
    """
    return subject, _wrap(f"Order {order.order_id} confirmed", body)


def render_order_status_email(order: "Order", status: str) -> tuple[str, str] | None:
    copy = SHIPMENT_STATUS_COPY.get(status)
    if not copy:
        return None
    title, message = copy
    address = order.shipping_address
    tracking_html = ""
    if order.tracking_url:
        tracking_html = f"""
        <p style="margin-top:20px;">
          <a href="{order.tracking_url}" style="display:inline-block;background:{BRAND_COLOR};color:#ffffff;padding:12px 24px;text-decoration:none;border-radius:4px;">Track your order</a>
        </p>
        """
    subject = f"{title} — Order {order.order_id}"
    body = f"""
    <p>Hi {address.full_name},</p>
    <p>{message}</p>
    <p style="margin:20px 0 8px;"><strong>Order #{order.order_id}</strong></p>
    {tracking_html}
    """
    return subject, _wrap(title, body)
