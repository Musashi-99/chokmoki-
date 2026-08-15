from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence, Union

TWOPLACE = Decimal("0.01")
NumberLike = Union[Decimal, float, int, str, None]


def _decimal(x: NumberLike) -> Decimal:
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def money(x: NumberLike) -> float:
    return float(_decimal(x).quantize(TWOPLACE, ROUND_HALF_UP))


def inr_to_paise(amount: NumberLike) -> int:
    quantized = _decimal(amount).quantize(TWOPLACE, ROUND_HALF_UP)
    return int((quantized * 100).to_integral_value(ROUND_HALF_UP))


def paise_to_inr(paise) -> float:
    return money(_decimal(int(paise or 0)) / Decimal("100"))


def allocate_shares(
    amounts: Sequence[float],
    share: float,
    mask: Optional[Sequence[bool]] = None,
) -> list[float]:
    values = [money(a) for a in amounts]
    n = len(values)
    eligible = list(mask) if mask is not None else [True] * n
    if len(eligible) != n:
        raise ValueError("mask length must match amounts")
    eligible_indexes = [i for i, ok in enumerate(eligible) if ok]
    eligible_sum = money(sum(values[i] for i in eligible_indexes))
    cap = money(min(max(0, share), eligible_sum))
    out = [0.0] * n
    if cap <= 0 or eligible_sum <= 0:
        return out
    remaining = _decimal(cap)
    last = len(eligible_indexes) - 1
    cap_d = _decimal(cap)
    sum_d = _decimal(eligible_sum)
    for k, i in enumerate(eligible_indexes):
        if k == last:
            out[i] = money(remaining)
        else:
            part = money(cap_d * _decimal(values[i]) / sum_d)
            out[i] = part
            remaining -= _decimal(part)
    return out
