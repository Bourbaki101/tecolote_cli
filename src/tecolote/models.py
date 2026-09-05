from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class Extra:
    description: str
    amount_cents: int
    assignment: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "description": self.description,
            "amountCents": self.amount_cents,
            **({"assignment": self.assignment} if self.assignment else {}),
        }


@dataclass(frozen=True, slots=True)
class LineItem:
    description: str
    amount_cents: int
    kind: str

    def to_dict(self) -> dict[str, object]:
        return {"description": self.description, "amountCents": self.amount_cents, "kind": self.kind}


@dataclass(frozen=True, slots=True)
class InvoicePlan:
    invoice_number: int
    month: str
    period: str
    issue_date: str
    lines: tuple[LineItem, ...]
    base_cents: int
    extras_cents: int
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    relative_output_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "invoiceNumber": self.invoice_number,
            "month": self.month,
            "period": self.period,
            "issueDate": self.issue_date,
            "lines": [line.to_dict() for line in self.lines],
            "baseCents": self.base_cents,
            "extrasCents": self.extras_cents,
            "subtotalCents": self.subtotal_cents,
            "taxCents": self.tax_cents,
            "totalCents": self.total_cents,
            "relativeOutputPath": self.relative_output_path,
        }
