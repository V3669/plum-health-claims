from decimal import ROUND_HALF_EVEN, Decimal


def quantize(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
