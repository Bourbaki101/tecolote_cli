from __future__ import annotations

import pytest

from tecolote.errors import ValidationError
from tecolote.money import format_money, parse_major_units, split_monthly
from tecolote.periods import parse_month


@pytest.mark.parametrize(
    ("value", "expected"),
    [("2026-01", 31), ("2026-04", 30), ("2026-02", 28), ("2028-02", 29)],
)
def test_last_day(value: str, expected: int) -> None:
    assert parse_month(value).last_day == expected


def test_money_is_integer_safe() -> None:
    assert split_monthly(217000) == (108500, 108500)
    assert parse_major_units("50") == 5000
    assert parse_major_units("50.25") == 5025
    assert format_money(217000) == "USD 2,170.00"


@pytest.mark.parametrize("value", ["1.001", "nan", "-1", "not-money"])
def test_invalid_money(value: str) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_major_units(value)
    assert caught.value.code == "INVALID_AMOUNT"


def test_odd_monthly_cents_cannot_produce_unequal_halves() -> None:
    with pytest.raises(ValidationError) as caught:
        split_monthly(101)
    assert caught.value.code == "UNEQUAL_HALF_AMOUNT"
