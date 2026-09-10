"""Invoice under-recovery, against the three real April 2026 invoices.

These are transcribed from the PDFs, so they are a regression on the actual
billing pattern rather than an illustration of it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.invoice import Category as C
from app.domain.invoice import Invoice, InvoiceLine, assess

D = Decimal

DE_MINIMIS = D("0.10")
MODELLED_LOW = D("0.3595")     # scenario A, conservative
MODELLED_HIGH = D("0.4642")    # scenario C, upper bound
FRINGE = D("0.2245")


def line(cat, amount, desc="", who="") -> InvoiceLine:
    return InvoiceLine.of(cat, amount, desc, who)


# Invoice 10023 — Hybrid Phase II. Billed to 236 W Boardman Street, no PO,
# Net 30. Five people on one labour line of 1,374.00 and no indirect.
HYBRID = Invoice(
    invoice_id="10023", objective_id="HYBRID-II",
    po_number="", bill_to="236 W Boardman Street",
    lines=(
        line(C.LABOR, "1374.00", "April 2026 - Labor",
             "Gaffney, Negro, Longo, Jaric, Metzinger"),
        line(C.TRAVEL, "0.00"),
        line(C.ODC, "0.00"),
        line(C.CONSULTANT, "0.00", "Rich Lonardo"),
    ))

# Invoice 10018 — Drive AM, PO 20240119. Labour plus ODCs, no indirect.
DRIVE_AM = Invoice(
    invoice_id="10018", objective_id="DRIVE-AM",
    po_number="20240119", bill_to="NCDMM - America Makes",
    lines=(
        line(C.LABOR, "18448.11", "DRIVE AM Project - April 2026",
             "Engel, Gaffney, Kale, Negro, Jaric"),
        line(C.TRAVEL, "0.00"),
        line(C.MATERIALS, "0.00"),
        line(C.CONSULTANT, "0.00"),
        line(C.ODC, "19145.79"),
    ))

# Invoice 10039 — Last Tactical Mile, PO 20250018. The only one carrying an
# indirect line, and it is a flat 3,000.00.
LTM = Invoice(
    invoice_id="10039", objective_id="LTM",
    po_number="20250018", bill_to="NCDMM - America Makes",
    lines=(
        line(C.OTHER, "0.00", "Impact 2.0 The Last Tactical Mile - April 2026"),
        line(C.LABOR, "7493.52", "Labor", "Engel, Gaffney"),
        line(C.TRAVEL, "0.00"),
        line(C.MATERIALS, "0.00"),
        line(C.CONSULTANT, "8500.00"),
        line(C.INDIRECT, "3000.00"),
    ))

ALL = [HYBRID, DRIVE_AM, LTM]


# ------------------------------------------------------------ the face


@pytest.mark.parametrize("inv,total", [(HYBRID, "1374.00"),
                                       (DRIVE_AM, "37593.90"),
                                       (LTM, "18993.52")])
def test_invoices_foot_to_their_printed_totals(inv, total):
    assert inv.total == D(total)


def test_mtdc_picks_up_odcs_not_just_labor():
    """The controller's tabs track Labor only. Invoice 10018 is more than half
    ODCs, so labour-only tracking misses 19,145.79 of a 37,593.90 invoice."""
    assert DRIVE_AM.by_category(C.LABOR) == D("18448.11")
    assert DRIVE_AM.by_category(C.ODC) == D("19145.79")
    assert DRIVE_AM.mtdc_as_billed == D("37593.90")


def test_two_of_three_carry_no_indirect_at_all():
    assert HYBRID.carries_no_indirect
    assert DRIVE_AM.carries_no_indirect
    assert not LTM.carries_no_indirect


def test_none_of_them_carry_a_fringe_line():
    assert all(i.carries_no_fringe for i in ALL)


def test_the_ltm_indirect_is_not_a_rate():
    """3,000.00 on a base of 15,993.52 is 18.76% — not de minimis, and not any
    rate. It is the budgeted indirect straight-lined over the period of
    performance: 81,772.76 / 27 months = 3,028.62."""
    assert LTM.effective_indirect_rate == D("0.187576")
    assert LTM.indirect_billed != (LTM.mtdc_as_billed * DE_MINIMIS).quantize(D("0.01"))
    monthly_budget = (D("81772.76") / 27).quantize(D("0.01"))
    assert abs(LTM.indirect_billed - monthly_budget) < D("30")


# ------------------------------------------------------ under-recovery


def test_hybrid_forgoes_indirect_outright():
    r = assess(HYBRID, indirect_rate=DE_MINIMIS)
    assert r.indirect_billed == 0
    assert r.indirect_supported == D("137.40")
    assert r.under_recovered
    assert "No indirect line" in r.findings[0]


def test_drive_am_forgoes_the_most_because_of_the_odcs():
    r = assess(DRIVE_AM, indirect_rate=DE_MINIMIS)
    assert r.indirect_supported == D("3759.39")
    assert r.indirect_variance == D("3759.39")


def test_ltm_over_collects_against_de_minimis():
    """The one invoice with an indirect line bills more than de minimis would.
    Reporting only under-recovery would be advocacy, not analysis."""
    r = assess(LTM, indirect_rate=DE_MINIMIS)
    assert r.indirect_supported == D("1599.35")
    assert r.indirect_variance == D("-1400.65")
    assert not r.under_recovered
    assert "over-collected" in r.findings[0]
    assert "returnable" in r.findings[0]


def test_ltm_under_recovers_against_a_real_rate():
    r = assess(LTM, indirect_rate=MODELLED_LOW)
    assert r.indirect_variance > 0
    assert r.under_recovered


@pytest.mark.parametrize("rate,expected", [
    (DE_MINIMIS, "2496.14"),
    (MODELLED_LOW, "16758.63"),
    (MODELLED_HIGH, "22513.09"),
])
def test_one_month_across_all_three(rate, expected):
    total = sum((assess(i, indirect_rate=rate).indirect_variance for i in ALL),
                D(0))
    assert total == D(expected)


# ------------------------------------------------------------- fringe


def test_unburdened_labor_adds_fringe_and_widens_the_base():
    """If the labour lines are raw wages, fringe was never billed either — and
    the indirect base should have included it."""
    burdened = assess(DRIVE_AM, indirect_rate=DE_MINIMIS, fringe_rate=FRINGE,
                      labor_is_burdened=True)
    raw = assess(DRIVE_AM, indirect_rate=DE_MINIMIS, fringe_rate=FRINGE,
                 labor_is_burdened=False)

    assert burdened.fringe_supported == 0
    assert raw.fringe_supported == D("4141.60")
    assert raw.indirect_supported > burdened.indirect_supported
    assert raw.total_variance > burdened.total_variance
    assert any("No fringe line" in f for f in raw.findings)


def test_the_burdened_reading_is_not_assumed():
    """The invoice face cannot distinguish the two readings, so the caller
    states which is being tested and both are available."""
    a = assess(LTM, indirect_rate=DE_MINIMIS, fringe_rate=FRINGE,
               labor_is_burdened=True)
    b = assess(LTM, indirect_rate=DE_MINIMIS, fringe_rate=FRINGE,
               labor_is_burdened=False)
    assert a.total_variance != b.total_variance


# --------------------------------------------------------- direction


def test_variance_reports_both_directions():
    over = assess(LTM, indirect_rate=DE_MINIMIS)
    under = assess(DRIVE_AM, indirect_rate=DE_MINIMIS)
    assert over.indirect_variance < 0
    assert under.indirect_variance > 0


def test_an_empty_invoice_has_no_effective_rate():
    empty = Invoice(invoice_id="X", objective_id="LTM")
    assert empty.effective_indirect_rate is None
    assert empty.mtdc_as_billed == 0


def test_equipment_stays_out_of_the_base():
    inv = Invoice(invoice_id="E", objective_id="LTM", lines=(
        line(C.LABOR, "1000.00"), line(C.EQUIPMENT, "50000.00")))
    assert inv.mtdc_as_billed == D("1000.00")
    assert assess(inv, indirect_rate=DE_MINIMIS).indirect_supported == D("100.00")
