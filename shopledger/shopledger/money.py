"""Money handling. Amounts are stored as integers in the smallest currency unit,
so there are no floating-point rounding errors in your books."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def parse_money(text, decimals: int = 0) -> int:
    """'1,500' -> 1500 (decimals=0)   |   '12.50' -> 1250 (decimals=2)"""
    try:
        value = Decimal(str(text).replace(",", "").strip())
    except InvalidOperation:
        raise ValueError(f"invalid amount: {text!r}") from None
    if not value.is_finite() or value < 0:
        raise ValueError(f"amount must be a non-negative number, got {text!r}")
    return int((value * (10 ** decimals)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def format_money(amount: int, decimals: int = 0, currency: str = "UGX") -> str:
    if decimals == 0:
        body = f"{amount:,}"
    else:
        body = f"{Decimal(amount) / (10 ** decimals):,.{decimals}f}"
    return f"{currency} {body}"


def plain_money(amount: int, decimals: int = 0) -> str:
    """Machine-friendly (for CSV): no currency, no thousands separators."""
    if decimals == 0:
        return str(amount)
    return f"{Decimal(amount) / (10 ** decimals):.{decimals}f}"
