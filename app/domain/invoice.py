"""Invoice under-recovery and restatement.

What the three sample invoices show is a cost-reimbursement instrument billed
as though it were a mix of fixed price and time-and-materials: flat monthly
amounts, quantity one at a rate equal to the whole amount, no hours, no
burdened labour rate, and on two of three no indirect line at all.

The consequence is one-directional. Billing a straight-lined budget draw
against a cost-reimbursement award under-recovers whenever incurred cost
exceeds the draw, and recovers nothing at all for burden that was never on the
invoice. Nobody notices, because the invoice foots and gets paid.

This module quantifies that, per invoice, against a rate set — and it does so
in both directions, because the same arithmetic that finds under-recovery on
one award finds over-collection on another. Hybrid Phase 2 was billed at more
than twice its actual cost; Drive AM carried no indirect at all. Reporting only
the favourable half would be advocacy, not analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from .core import money

__all__ = [
    "Category",
    "InvoiceLine",
    "Invoice",
    "Recovery",
    "MTDC_CATEGORIES",
    "assess",
]


class Category(StrEnum):
    LABOR = "LABOR"
    FRINGE = "FRINGE"
    TRAVEL = "TRAVEL"
    MATERIALS = "MATERIALS"
    CONSULTANT = "CONSULTANT"
    SUBAWARD = "SUBAWARD"
    ODC = "ODC"
    EQUIPMENT = "EQUIPMENT"
    INDIRECT = "INDIRECT"
    FEE = "FEE"
    OTHER = "OTHER"


#: In the modified total direct cost base per 2 CFR 200.1. Equipment is
#: excluded; subawards are included only to the per-subaward cap, which is
#: applied upstream in ``burden.build_mtdc_base`` because it needs to see the
#: individual subawards rather than a category total.
MTDC_CATEGORIES = frozenset({
    Category.LABOR, Category.FRINGE, Category.TRAVEL, Category.MATERIALS,
    Category.CONSULTANT, Category.SUBAWARD, Category.ODC,
})


@dataclass(frozen=True)
class InvoiceLine:
    category: Category
    amount: Decimal
    description: str = ""
    personnel: str = ""

    @classmethod
    def of(cls, category: Category, amount, description: str = "",
           personnel: str = "") -> "InvoiceLine":
        return cls(category=category, amount=money(amount),
                   description=description, personnel=personnel)


@dataclass(frozen=True)
class Invoice:
    invoice_id: str
    objective_id: str
    lines: tuple[InvoiceLine, ...] = field(default_factory=tuple)
    po_number: str = ""
    bill_to: str = ""

    def by_category(self, category: Category) -> Decimal:
        return money(sum((l.amount for l in self.lines if l.category is category),
                         Decimal(0)))

    @property
    def total(self) -> Decimal:
        return money(sum((l.amount for l in self.lines), Decimal(0)))

    @property
    def mtdc_as_billed(self) -> Decimal:
        """The direct cost on the face of the invoice that carries indirect."""
        return money(sum((l.amount for l in self.lines
                          if l.category in MTDC_CATEGORIES), Decimal(0)))

    @property
    def indirect_billed(self) -> Decimal:
        return self.by_category(Category.INDIRECT)

    @property
    def fringe_billed(self) -> Decimal:
        return self.by_category(Category.FRINGE)

    @property
    def carries_no_indirect(self) -> bool:
        return self.indirect_billed == 0

    @property
    def carries_no_fringe(self) -> bool:
        """No fringe line at all.

        Not conclusive on its own: a labour line may be burdened already. It is
        conclusive when read with the labour distribution, which is why the
        finding says "verify" rather than asserting."""
        return self.fringe_billed == 0

    @property
    def effective_indirect_rate(self) -> Decimal | None:
        base = self.mtdc_as_billed
        if base == 0:
            return None
        return (self.indirect_billed / base).quantize(Decimal("0.000001"))


@dataclass(frozen=True)
class Recovery:
    """What an invoice recovered against what the rate set supports."""

    invoice_id: str
    objective_id: str
    mtdc_as_billed: Decimal
    indirect_billed: Decimal
    indirect_supported: Decimal
    fringe_billed: Decimal
    fringe_supported: Decimal
    rate_label: str = ""

    @property
    def indirect_variance(self) -> Decimal:
        """Positive means under-recovered; negative means over-collected."""
        return money(self.indirect_supported - self.indirect_billed)

    @property
    def fringe_variance(self) -> Decimal:
        return money(self.fringe_supported - self.fringe_billed)

    @property
    def total_variance(self) -> Decimal:
        return money(self.indirect_variance + self.fringe_variance)

    @property
    def under_recovered(self) -> bool:
        return self.total_variance > 0

    @property
    def findings(self) -> list[str]:
        out: list[str] = []
        if self.indirect_billed == 0 and self.mtdc_as_billed > 0:
            out.append(
                f"No indirect line. On a cost-reimbursement award this forgoes "
                f"recovery outright: {self.indirect_supported} is supported on "
                f"an invoiced base of {self.mtdc_as_billed}.")
        elif self.indirect_variance > 0:
            out.append(
                f"Indirect under-recovered by {self.indirect_variance} "
                f"({self.indirect_billed} billed against "
                f"{self.indirect_supported} supported).")
        elif self.indirect_variance < 0:
            out.append(
                f"Indirect over-collected by {abs(self.indirect_variance)}. "
                f"This is returnable, not a negotiating position.")
        if self.fringe_billed == 0 and self.fringe_supported > 0:
            out.append(
                f"No fringe line. Verify whether the labour amount is already "
                f"burdened; if it is raw wages, {self.fringe_supported} of "
                f"fringe was never billed.")
        return out


def assess(invoice: Invoice, *, indirect_rate: Decimal,
           fringe_rate: Decimal = Decimal(0),
           labor_is_burdened: bool = True,
           rate_label: str = "") -> Recovery:
    """Measure one invoice against a rate set.

    ``labor_is_burdened`` says whether the labour line already carries fringe.
    The sample invoices give no way to tell from their face — quantity one at a
    rate equal to the whole amount — so the caller has to state which reading
    is being tested, and the answer says so.
    """
    base = invoice.mtdc_as_billed
    labor = invoice.by_category(Category.LABOR)

    fringe_supported = (Decimal(0) if labor_is_burdened
                        else money(labor * fringe_rate))

    # Fringe that was never billed also belongs in the base it would have
    # carried, so indirect is measured on the base as it should have stood.
    indirect_supported = money((base + fringe_supported) * indirect_rate)

    return Recovery(
        invoice_id=invoice.invoice_id,
        objective_id=invoice.objective_id,
        mtdc_as_billed=base,
        indirect_billed=invoice.indirect_billed,
        indirect_supported=indirect_supported,
        fringe_billed=invoice.fringe_billed,
        fringe_supported=fringe_supported,
        rate_label=rate_label,
    )
