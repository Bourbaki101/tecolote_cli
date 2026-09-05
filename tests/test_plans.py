from __future__ import annotations

from copy import deepcopy

import pytest

from tecolote.drafts import build_plans, parse_extra
from tecolote.errors import ValidationError


def test_monthly_plan_has_two_service_lines(isolated: dict[str, object]) -> None:
    config = isolated["config"]
    _, plans = build_plans(config, "2026-09", 11, [parse_extra("SLA Bonus=50")])  # type: ignore[arg-type]
    assert len(plans) == 1
    plan = plans[0]
    assert plan.invoice_number == 11
    assert plan.issue_date == "2026-09-16"
    assert [line.amount_cents for line in plan.lines[:2]] == [108500, 108500]
    assert plan.base_cents == 217000
    assert plan.extras_cents == 5000
    assert plan.total_cents == 222000
    assert "September (16-30)" in plan.lines[1].description
    assert plan.relative_output_path == "2026/September/Invoice_011_September_2026.pdf"


def test_monthly_date_override(isolated: dict[str, object]) -> None:
    _, plans = build_plans(isolated["config"], "2026-09", 11, [], issue_date="2026-09-18")  # type: ignore[arg-type]
    assert plans[0].issue_date == "2026-09-18"


def test_twice_monthly_plans_and_extra_assignments(isolated: dict[str, object]) -> None:
    config = deepcopy(isolated["config"])
    config["compensation"]["schedule"] = "twice-monthly"
    extras = [
        parse_extra("First=10:first"),
        parse_extra("Second=20:second"),
        parse_extra("Both=50:both"),
    ]
    _, plans = build_plans(config, "2028-02", 20, extras)
    assert len(plans) == 2
    assert [plan.invoice_number for plan in plans] == [20, 21]
    assert [plan.issue_date for plan in plans] == ["2028-02-10", "2028-02-20"]
    assert [plan.period for plan in plans] == ["01-15", "16-29"]
    assert plans[0].extras_cents == 6000
    assert plans[1].extras_cents == 7000
    assert plans[0].total_cents == 114500
    assert plans[1].total_cents == 115500


def test_both_adds_full_amount_to_each_invoice(isolated: dict[str, object]) -> None:
    config = deepcopy(isolated["config"])
    config["compensation"]["schedule"] = "twice-monthly"
    _, plans = build_plans(config, "2026-09", 11, [parse_extra("SLA Bonus=50:both")])
    assert [plan.extras_cents for plan in plans] == [5000, 5000]


def test_twice_monthly_requires_assignment(isolated: dict[str, object]) -> None:
    config = deepcopy(isolated["config"])
    config["compensation"]["schedule"] = "twice-monthly"
    with pytest.raises(ValidationError) as caught:
        build_plans(config, "2026-09", 11, [parse_extra("SLA Bonus=50")])
    assert caught.value.code == "INVALID_EXTRA"


def test_unknown_extra_assignment_is_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        parse_extra("SLA Bonus=50:third")
    assert caught.value.code == "INVALID_EXTRA"
