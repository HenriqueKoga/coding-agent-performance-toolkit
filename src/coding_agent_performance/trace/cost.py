"""Safe USD to microdollar conversion."""

from decimal import ROUND_HALF_EVEN, Decimal, DecimalException

_MICROS_PER_USD = Decimal("1000000")


def usd_to_micros(value: object) -> int:
    """Convert a USD amount to integer micros, or 0 if it is not representable."""
    if isinstance(value, bool) or not isinstance(value, int | float | str | Decimal):
        return 0
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            return 0
        micros = (amount * _MICROS_PER_USD).to_integral_value(rounding=ROUND_HALF_EVEN)
        return int(micros)
    except DecimalException, ValueError, TypeError, OverflowError:
        return 0
