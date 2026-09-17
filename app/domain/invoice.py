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
    "DirectCost",
    "Rebuild",
    "MTDC_CATEGORIES",
    "assess",
    "rebuild",
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
        """No separate fringe line.

        On these invoices that is not a gap: fringe is inside the labour
        amount. The absence of a line is a presentation fact, not a recovery
        one, and treating it as foregone recovery would overstate the claim."""
        return self.fringe_billed == 0

    def labor_composition(self, fringe_rate: Decimal) -> tuple[Decimal, Decimal]:
        """Split a burdened labour amount into base wages and embedded fringe.

        The invoice face shows one number at quantity one, so the split has to
        be derived: base = burdened / (1 + fringe). Needed to test the labour
        line against payroll and the effort distribution, which are stated in
        base wages — comparing a burdened invoice line to a wage control finds
        a difference that is only the fringe.
        """
        burdened = self.by_category(Category.LABOR) + self.fringe_billed
        if fringe_rate <= 0:
            return money(burdened), Decimal(0)
        base = money(burdened / (Decimal(1) + fringe_rate))
        return base, money(burdened - base)

    @property
    def effective_indirect_rate(self) -> Decimal | None:
        base = self.mtdc_as_billed
        if base == 0:
            return None
        return (self.indirect_billed / base).quantize(Decimal("0.000001"))

    @property
    def base_is_assessable(self) -> bool:
        """Can an indirect base be read off the face of this invoice at all?

        Digital Engineering bills one undifferentiated line a month — "YBI
        Total: January 2025" — which is `OTHER`, and `OTHER` is not an MTDC
        category. So `mtdc_as_billed` is zero on $579,074.25 of billing and
        the invoice-only reading reports a variance of exactly 0.00.

        Zero and *not assessable from this document* are different answers,
        and a reading that cannot tell them apart will report the second as
        the first every time. This is what lets a caller say which.
        """
        return not (self.total > 0 and self.mtdc_as_billed == 0)


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
    #: The invoice's own total. Carried so `findings` can tell a base of zero
    #: on a zero invoice from a base of zero on $579,074.25 of billing.
    billed_total: Decimal = Decimal(0)
    base_wages: Decimal = Decimal(0)
    embedded_fringe: Decimal = Decimal(0)
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
        if self.billed_total > 0 and self.mtdc_as_billed == 0:
            # Reported before anything else, because every figure below it on
            # this reading is zero and a reader will take that for a finding
            # of "nothing owed" rather than "nothing measurable".
            out.append(
                f"NOT ASSESSABLE from the invoice: {self.billed_total:,.2f} "
                f"billed and no line in an MTDC category, so there is no base "
                f"to apply a rate to. This is not a variance of zero. The "
                f"rebuilt position against the cost record is the figure to "
                f"read.")
        elif self.indirect_billed == 0 and self.mtdc_as_billed > 0:
            out.append(
                f"No indirect line. On a cost-reimbursement award this forgoes "
                f"recovery outright: {self.indirect_supported:,.2f} is "
                f"supported on an invoiced base of {self.mtdc_as_billed:,.2f}.")
        elif self.indirect_variance > 0:
            out.append(
                f"Indirect under-recovered by {self.indirect_variance:,.2f} "
                f"({self.indirect_billed:,.2f} billed against "
                f"{self.indirect_supported:,.2f} supported).")
        elif self.indirect_variance < 0:
            out.append(
                f"Indirect over-collected by {abs(self.indirect_variance):,.2f}. "
                f"This is returnable, not a negotiating position.")
        return out


def assess(invoice: Invoice, *, indirect_rate: Decimal,
           fringe_rate: Decimal = Decimal(0),
           labor_is_burdened: bool = True,
           rate_label: str = "") -> Recovery:
    """Measure one invoice against a rate set.

    ``labor_is_burdened`` says whether the labour line already carries fringe.
    On the America Makes invoices it does, which is the default: the labour
    amount is burdened and fringe is not separately foregone. Fringe is part of
    MTDC either way, so the indirect base is unaffected by the reading — what
    changes is whether unbilled fringe is added to the claim, and on these
    invoices it must not be.
    """
    base = invoice.mtdc_as_billed
    labor = invoice.by_category(Category.LABOR)

    fringe_supported = (Decimal(0) if labor_is_burdened
                        else money(labor * fringe_rate))
    base_wages, embedded_fringe = (invoice.labor_composition(fringe_rate)
                                   if labor_is_burdened
                                   else (labor, money(labor * fringe_rate)))

    # Fringe that was never billed also belongs in the base it would have
    # carried, so indirect is measured on the base as it should have stood.
    indirect_supported = money((base + fringe_supported) * indirect_rate)

    return Recovery(
        invoice_id=invoice.invoice_id,
        objective_id=invoice.objective_id,
        mtdc_as_billed=base,
        billed_total=invoice.total,
        indirect_billed=invoice.indirect_billed,
        indirect_supported=indirect_supported,
        fringe_billed=invoice.fringe_billed,
        fringe_supported=fringe_supported,
        base_wages=base_wages,
        embedded_fringe=embedded_fringe,
        rate_label=rate_label,
    )


# ── Rebuilding a year, rather than adding to an invoice ──────────────────


@dataclass(frozen=True)
class DirectCost:
    """What the cost record carries for one objective over one period.

    Passed in rather than looked up: `domain/` does not import `app.db`, and
    keeping it that way is what lets the arithmetic below be tested without a
    database.
    """
    wages: Decimal
    fringe: Decimal
    nonlabour: Decimal
    mtdc: Decimal

    @property
    def total(self) -> Decimal:
        return money(self.wages + self.fringe + self.nonlabour)


@dataclass(frozen=True)
class Rebuild:
    """A year of invoices against the cost record, at one rate.

    `position` is signed on purpose and is never netted with anything: money
    to ask for and money to give back are two conversations, and a single
    figure hides both.
    """
    objective_id: str
    invoices: int
    billed: Decimal
    direct_supported: Decimal
    indirect_supported: Decimal
    indirect_billed: Decimal
    elected_rate: Decimal
    elected_indirect: Decimal
    as_billed_base: Decimal
    as_billed_indirect: Decimal
    rate: Decimal

    @property
    def supported(self) -> Decimal:
        return money(self.direct_supported + self.indirect_supported)

    @property
    def position(self) -> Decimal:
        """Positive is under-recovered; negative is over-billed."""
        return money(self.supported - self.billed)

    @property
    def implied_rate(self) -> Decimal | None:
        """The indirect rate actually recovered.

        What was billed, less the direct cost the record carries, over the
        MTDC base. Two readings and this does not choose between them: YBI
        billed above cost, or the classification has not attributed enough
        cost to the objective.
        """
        if self.as_billed_base == 0 and self.billed == 0:
            return None
        base = self.indirect_supported / self.rate if self.rate else Decimal(0)
        if base == 0:
            return None
        return ((self.billed - self.direct_supported) / base).quantize(
            Decimal("0.000001"))

    @property
    def as_billed_position(self) -> Decimal:
        """What the invoice-only reading says, for comparison and never as
        the position. It applies the rate to a base that already carries
        embedded indirect."""
        return money(self.as_billed_indirect - self.indirect_billed)

    @property
    def findings(self) -> list[str]:
        out: list[str] = []
        gap = self.as_billed_position - self.position
        if gap.copy_abs() > Decimal("0.01"):
            out.append(
                f"Reading the invoice alone would say {self.as_billed_position}; "
                f"rebuilding against the cost record says {self.position}. The "
                f"difference of {gap} is indirect claimed on labour that "
                f"already carries it.")
        if self.indirect_billed == 0 and self.billed > 0:
            out.append(
                f"No indirect line on any invoice, yet {self.implied_rate} is "
                f"the rate the billing actually recovered against an elected "
                f"{self.elected_rate}.")
        return out


def rebuild(objective_id: str, *, invoices: int, billed: Decimal,
            cost: DirectCost, indirect_rate: Decimal,
            elected_rate: Decimal = Decimal(0),
            indirect_billed: Decimal = Decimal(0),
            as_billed_base: Decimal = Decimal(0)) -> Rebuild:
    """What a year of invoices would have been, built from the cost record.

    The labour line comes **down** to wages plus fringe before indirect goes
    on. The invoices bill labour that already carries indirect — YBI's Hybrid
    cost proposal computes $45,457 of 10% ICR into a $449,043.40 labour line —
    so applying a rate to the billed labour claims it twice.

    It is annual rather than per-invoice because the cost record is annual.
    Splitting a year of classified cost across twelve invoices needs a driver
    nobody has recorded, and inventing one to make the shape match would be
    manufacturing precision.
    """
    return Rebuild(
        objective_id=objective_id,
        invoices=invoices,
        billed=money(billed),
        direct_supported=cost.total,
        indirect_supported=money(cost.mtdc * indirect_rate),
        indirect_billed=money(indirect_billed),
        elected_rate=elected_rate,
        elected_indirect=money(cost.mtdc * elected_rate),
        as_billed_base=money(as_billed_base),
        as_billed_indirect=money(as_billed_base * indirect_rate),
        rate=indirect_rate,
    )
