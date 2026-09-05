from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from .errors import ValidationError


@dataclass(frozen=True, slots=True)
class InvoiceMonth:
    year: int
    month: int

    @property
    def name(self) -> str:
        return calendar.month_name[self.month]

    @property
    def last_day(self) -> int:
        return calendar.monthrange(self.year, self.month)[1]

    @property
    def key(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def parse_month(value: str) -> InvoiceMonth:
    try:
        parsed = date.fromisoformat(f"{value}-01")
    except (ValueError, TypeError) as exc:
        raise ValidationError("INVALID_MONTH", "Month must use YYYY-MM format.") from exc
    if value != f"{parsed.year:04d}-{parsed.month:02d}":
        raise ValidationError("INVALID_MONTH", "Month must use zero-padded YYYY-MM format.")
    return InvoiceMonth(parsed.year, parsed.month)


def parse_issue_date(value: str, month: InvoiceMonth) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValidationError("INVALID_DATE", "Issue date must use YYYY-MM-DD format.") from exc
    if parsed.year != month.year or parsed.month != month.month:
        raise ValidationError("INVALID_DATE", "Issue date must fall within the selected month.")
    return parsed
