from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Iterable

from .config import write_json_secure
from .errors import FilesystemError, ValidationError
from .models import Extra, InvoicePlan, LineItem
from .money import parse_major_units, split_monthly
from .periods import InvoiceMonth, parse_issue_date, parse_month
from .state import drafts_dir


def parse_extra(value: str) -> Extra:
    try:
        description, amount_spec = value.rsplit("=", 1)
    except ValueError as exc:
        raise ValidationError(
            "INVALID_EXTRA", "Extra must use DESCRIPTION=AMOUNT[:first|second|both]."
        ) from exc
    assignment = None
    amount = amount_spec
    if ":" in amount_spec:
        amount, assignment = amount_spec.rsplit(":", 1)
        if assignment not in {"first", "second", "both"}:
            raise ValidationError("INVALID_EXTRA", f"Unknown extra assignment: {assignment}.")
    description = description.strip()
    if not description:
        raise ValidationError("INVALID_EXTRA", "Extra description cannot be empty.")
    return Extra(description, parse_major_units(amount), assignment)


def _output_name(number: int, month: InvoiceMonth, period: str, schedule: str) -> str:
    if schedule == "monthly":
        return f"Invoice_{number:03d}_{month.name}_{month.year}.pdf"
    return f"Invoice_{number:03d}_{month.name}_{period}_{month.year}.pdf"


def _plan(
    number: int,
    month: InvoiceMonth,
    period: str,
    issue_date: date,
    service_lines: list[LineItem],
    extras: Iterable[Extra],
    schedule: str,
) -> InvoicePlan:
    extra_lines = [LineItem(extra.description, extra.amount_cents, "extra") for extra in extras]
    lines = tuple(service_lines + extra_lines)
    base = sum(line.amount_cents for line in service_lines)
    extra_total = sum(line.amount_cents for line in extra_lines)
    subtotal = base + extra_total
    relative = str(PurePosixPath(str(month.year)) / month.name / _output_name(number, month, period, schedule))
    return InvoicePlan(
        number,
        month.key,
        period,
        issue_date.isoformat(),
        lines,
        base,
        extra_total,
        subtotal,
        0,
        subtotal,
        relative,
    )


def build_plans(
    config: dict[str, Any],
    month_value: str,
    next_number: int,
    extras: list[Extra],
    issue_date: str | None = None,
    first_date: str | None = None,
    second_date: str | None = None,
) -> tuple[InvoiceMonth, list[InvoicePlan]]:
    month = parse_month(month_value)
    schedule = config["compensation"]["schedule"]
    first_half, second_half = split_monthly(config["compensation"]["monthlyCents"])

    if schedule == "monthly":
        if first_date or second_date:
            raise ValidationError("INVALID_DATE", "--first-date and --second-date require twice-monthly schedule.")
        if any(extra.assignment for extra in extras):
            raise ValidationError("INVALID_EXTRA", "Extra assignment is unnecessary for monthly schedule.")
        issued = parse_issue_date(issue_date, month) if issue_date else date(month.year, month.month, 16)
        services = [
            LineItem(f"Consulting services covering the period of {month.name} (1-15)", first_half, "service"),
            LineItem(
                f"Consulting services covering the period of {month.name} (16-{month.last_day})",
                second_half,
                "service",
            ),
        ]
        return month, [_plan(next_number, month, "full-month", issued, services, extras, schedule)]

    if issue_date:
        raise ValidationError("INVALID_DATE", "Use --first-date and --second-date for twice-monthly schedule.")
    if any(extra.assignment is None for extra in extras):
        raise ValidationError(
            "INVALID_EXTRA", "Twice-monthly extras require :first, :second, or :both assignment."
        )
    issued_first = parse_issue_date(first_date, month) if first_date else date(month.year, month.month, 10)
    issued_second = parse_issue_date(second_date, month) if second_date else date(month.year, month.month, 20)
    first_extras = [extra for extra in extras if extra.assignment in {"first", "both"}]
    second_extras = [extra for extra in extras if extra.assignment in {"second", "both"}]
    first_period = "01-15"
    second_period = f"16-{month.last_day}"
    return month, [
        _plan(
            next_number,
            month,
            first_period,
            issued_first,
            [LineItem(f"Consulting services covering the period of {month.name} (1-15)", first_half, "service")],
            first_extras,
            schedule,
        ),
        _plan(
            next_number + 1,
            month,
            second_period,
            issued_second,
            [
                LineItem(
                    f"Consulting services covering the period of {month.name} (16-{month.last_day})",
                    second_half,
                    "service",
                )
            ],
            second_extras,
            schedule,
        ),
    ]


def create_draft(
    config: dict[str, Any],
    month_value: str,
    next_number: int,
    extras: list[Extra],
    issue_date: str | None = None,
    first_date: str | None = None,
    second_date: str | None = None,
) -> dict[str, Any]:
    month, plans = build_plans(
        config, month_value, next_number, extras, issue_date, first_date, second_date
    )
    core = {
        "schemaVersion": 1,
        "month": month.key,
        "schedule": config["compensation"]["schedule"],
        "expectedNextInvoiceNumber": next_number,
        "configSnapshot": config,
        "invoices": [plan.to_dict() for plan in plans],
    }
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    draft_id = hashlib.sha256(canonical).hexdigest()[:16]
    draft = {
        "draftId": draft_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        **core,
    }
    write_json_secure(drafts_dir() / f"{draft_id}.json", draft)
    return draft


def load_draft(draft_id: str) -> dict[str, Any]:
    if not draft_id or any(character not in "0123456789abcdef" for character in draft_id) or len(draft_id) != 16:
        raise ValidationError("DRAFT_NOT_FOUND", "Draft not found.")
    path = drafts_dir() / f"{draft_id}.json"
    if not path.exists():
        raise ValidationError("DRAFT_NOT_FOUND", "Draft not found.")
    try:
        draft = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError("DRAFT_INVALID", "Stored draft is unreadable or invalid.") from exc
    if not isinstance(draft, dict) or draft.get("draftId") != draft_id or draft.get("schemaVersion") != 1:
        raise ValidationError("DRAFT_INVALID", "Stored draft has an invalid schema.")
    return draft


def delete_draft(draft_id: str) -> None:
    try:
        (drafts_dir() / f"{draft_id}.json").unlink(missing_ok=True)
    except OSError as exc:
        raise FilesystemError("Invoice committed, but the draft could not be removed.") from exc
