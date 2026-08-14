from decimal import Decimal, ROUND_HALF_UP

from src.models.coupon import DiscountIndicator, DiscountType


def money(x) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def _attr(obj, name):
    if isinstance(obj, dict):
        return obj[name]
    return getattr(obj, name)


def compute_discount(items, coupon, shipping=0):
    subtotal = money(sum(_attr(item, "total_price") for item in items))
    coupon_type = _attr(coupon, "type")
    indicator = _attr(coupon, "indicator")
    amount = _attr(coupon, "amount")

    if coupon_type == DiscountType.PRODUCT:
        product_id = _attr(coupon, "product_id")
        matching = [item for item in items if _attr(item, "product_id") == product_id]
        if not matching:
            raise ValueError("Coupon does not apply to this cart")
        eligible = money(sum(_attr(item, "total_price") for item in matching))
    else:
        eligible = subtotal

    if indicator == DiscountIndicator.PERCENT:
        computed = money(eligible * amount / 100)
    else:
        computed = money(min(amount, eligible))

    computed = min(computed, subtotal)
    total = money(max(0, subtotal - computed + shipping))
    return computed, total, subtotal


class DiscountService:
    def compute(self, items, coupon, shipping=0):
        return compute_discount(items, coupon, shipping)
