from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .errors import ValidationError


def parse_major_units(value: str) -> int:
    try:
        amount = Decimal(value.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValidationError("INVALID_AMOUNT", f"Invalid monetary amount: {value!r}.") from exc
    if not amount.is_finite() or amount < 0:
        raise ValidationError("INVALID_AMOUNT", "Amounts must be finite and non-negative.")
    cents = amount * 100
    rounded = cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if cents != rounded:
        raise ValidationError("INVALID_AMOUNT", "Amounts may have at most two decimal places.")
    return int(rounded)


def split_monthly(monthly_cents: int) -> tuple[int, int]:
    if monthly_cents < 0:
        raise ValidationError("INVALID_AMOUNT", "Monthly compensation cannot be negative.")
    if monthly_cents % 2:
        raise ValidationError(
            "UNEQUAL_HALF_AMOUNT",
            "Monthly compensation must be an even number of minor units so both halves are equal.",
        )
    half = monthly_cents // 2
    return half, half


def format_money(cents: int, currency: str = "USD") -> str:
    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    return f"{currency} {sign}{absolute // 100:,}.{absolute % 100:02d}"
