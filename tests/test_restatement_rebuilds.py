"""A restatement rebuilds; it does not add.

The route measured indirect on the invoice's own base, and that base carries
labour which already contains embedded indirect. YBI's Hybrid Phase 2 cost
proposal shows the arithmetic — $403,570 of personnel and fringe plus $45,457
of 10% ICR presented as one labour line of $449,043.40 — so the rate went on
top of a figure that already held it.

Across the four America Makes awards the two readings differ by $722,095.49,
in the direction that would have YBI ask a federal pass-through for money it
cannot support. These hold the corrected arithmetic against the figures two
published workpapers derived independently, which is what makes them a check
rather than a restatement of the code.

No database: the rebuild is pure, which is the point of passing the cost in.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from app.domain.invoice import (Category, DirectCost, Invoice, InvoiceLine,
                                assess, rebuild)

#: The sealed INDIRECT_COMBINED on the POOL basis **before any carve-out was
#: recorded**. It is deliberately frozen here rather than read from the live
#: rate: these tests prove the rebuild engine reproduces figures that were
#: derived by hand, months before this code existed, and a fixture that
#: followed the record would be the engine agreeing with itself.
#: The live rate is 24.71% — the same sealed judgments after the 200.465 and
#: 200.436(b) carve-outs — and the positions it produces are in
#: `docs/WP_AM_2025_RESTATED_INVOICES.md` and `docs/SETTLEMENT_2025.md`.
RATE = D("0.4399")
FRINGE = D("0.2190")
ELECTED = D("0.10")

#: Read off the live record: wages and fringe from the effort distribution,
#: non-labour from the DIRECT pool, MTDC from the allocation the rate
#: computation persisted.
DRIVE_AM = DirectCost(wages=D("147310.09"), fringe=D("32260.91"),
                      nonlabour=D("181880.88"), mtdc=D("361451.88"))
LTM = DirectCost(wages=D("52607.87"), fringe=D("11521.12"),
                 nonlabour=D("266384.07"), mtdc=D("330513.06"))


def drive_am(**kw):
    return rebuild("DRIVE-AM", invoices=12, billed=D("579240.87"),
                   cost=DRIVE_AM, indirect_rate=RATE, elected_rate=ELECTED,
                   indirect_billed=D("0"), as_billed_base=D("579240.87"), **kw)


def ltm(**kw):
    return rebuild("LTM", invoices=12, billed=D("368222.24"), cost=LTM,
                   indirect_rate=RATE, elected_rate=ELECTED,
                   indirect_billed=D("44400.00"),
                   as_billed_base=D("323822.24"), **kw)


# ────────────────────────────────── the published figures

def test_drive_am_reproduces_the_published_workpaper():
    """$(58,786.31) was derived by hand months before this code existed, at
    the 43.99% rate `RATE` holds. Reproducing it is the check; agreeing with
    myself would not be.

    It is **no longer the published Drive AM position** — the carve-outs
    took the rate to 24.71% and the position to $(128,474.23), which is what
    `docs/SETTLEMENT_2025.md` carries and what
    `tests/test_the_settlement_states_the_record.py` holds against the live
    record. This one anchors the arithmetic, not the paper."""
    assert drive_am().position == D("-58786.31")


def test_ltm_reproduces_the_published_workpaper():
    assert ltm().position == D("107683.52")


def test_only_ltm_is_under_recovered():
    """The direction matters more than the amount. Three of the four awards
    billed labour at or above full burden, so there is nothing left to claim
    on them; LTM billed at 1.40x and is 75.6% non-labour, which a loaded
    labour rate cannot reach at all."""
    assert drive_am().position < 0
    assert ltm().position > 0


# ────────────────────────────────── rebuild against add

def test_the_two_readings_differ_and_the_rebuild_is_the_lower():
    """If these ever converge, the labour has stopped being burdened and
    somebody should be told rather than the test quietly passing."""
    r = drive_am()
    assert r.as_billed_position == D("254808.06")
    assert r.position == D("-58786.31")
    assert r.as_billed_position > r.position


def test_the_difference_is_named_in_the_findings():
    r = drive_am()
    said = " ".join(r.findings)
    assert "254808.06" in said and "-58786.31" in said
    assert "already carries it" in said


def test_adding_the_rate_to_the_billed_base_is_what_double_counts():
    """State the mechanism rather than the number: the as-billed reading uses
    the invoice's base, the rebuild uses the cost record's."""
    r = drive_am()
    assert r.as_billed_indirect == (r.as_billed_base * RATE).quantize(D("0.01"))
    assert r.indirect_supported == (DRIVE_AM.mtdc * RATE).quantize(D("0.01"))
    assert r.as_billed_base > DRIVE_AM.mtdc


# ────────────────────────────────── the election, and what was recovered

def test_the_implied_rate_is_what_was_actually_recovered():
    """60.25% against an elected 10.00%, on an award whose invoices show no
    indirect line at all."""
    assert drive_am().implied_rate == D("0.602539")


def test_ltm_recovered_close_to_its_election():
    """LTM is the only award that billed an indirect line, and the only one
    whose executed Schedule B budgets the 10%."""
    assert ltm().implied_rate == D("0.114093")   # 37,709.18 / 330,513.06


def test_the_elected_indirect_is_on_the_rebuilt_base_not_the_billed_one():
    """The de minimis is charged on MTDC under 200.414(f). Applying it to the
    invoice's own base would make the same mistake in miniature."""
    r = drive_am()
    assert r.elected_indirect == (DRIVE_AM.mtdc * ELECTED).quantize(D("0.01"))
    assert r.elected_indirect == D("36145.19")


# ────────────────────────────────── supported foots to its parts

def test_supported_foots_to_direct_plus_indirect():
    r = drive_am()
    assert r.supported == r.direct_supported + r.indirect_supported


def test_direct_supported_is_wages_plus_fringe_plus_non_labour():
    assert DRIVE_AM.total == D("147310.09") + D("32260.91") + D("181880.88")
    assert drive_am().direct_supported == DRIVE_AM.total


def test_the_position_is_signed_and_never_netted():
    """Money to ask for and money to give back are two conversations. A
    Rebuild exposes one signed figure and no net of the two directions."""
    assert drive_am().position < 0 < ltm().position
    assert not hasattr(drive_am(), "net_movement")


# ────────────────────────────── a base that cannot be read is not zero

def lump_sum() -> Invoice:
    """Digital Engineering: one undifferentiated line a month."""
    return Invoice("9062", "DIG-ENG", lines=(
        InvoiceLine.of(Category.OTHER, "82724.89", "YBI Total: January 2025"),))


def test_a_lump_sum_invoice_has_no_assessable_base():
    assert lump_sum().base_is_assessable is False
    assert lump_sum().mtdc_as_billed == 0
    assert lump_sum().total == D("82724.89")


def test_a_lump_sum_says_not_assessable_rather_than_zero():
    """The engine reported exactly 0.00 on $579,074.25 of Digital Engineering
    billing, because OTHER is not an MTDC category. Zero and *not measurable
    from this document* are different answers and only one of them is true."""
    r = assess(lump_sum(), indirect_rate=RATE, fringe_rate=FRINGE)
    assert r.indirect_variance == 0
    assert "NOT ASSESSABLE" in r.findings[0]
    assert "not a variance of zero" in r.findings[0]


def test_an_ordinary_invoice_still_reports_its_missing_indirect():
    """The new branch must not swallow the finding it sits in front of."""
    inv = Invoice("9092", "DRIVE-AM", lines=(
        InvoiceLine.of(Category.LABOR, "25373.65"),
        InvoiceLine.of(Category.ODC, "3700.00"),))
    r = assess(inv, indirect_rate=RATE, fringe_rate=FRINGE)
    assert inv.base_is_assessable is True
    assert "No indirect line" in r.findings[0]


def test_a_genuinely_empty_invoice_is_assessable():
    """Zero billed and zero base is a real zero, not a gap."""
    inv = Invoice("x", "DRIVE-AM", lines=())
    assert inv.base_is_assessable is True


@pytest.mark.parametrize("category", [Category.OTHER, Category.FEE,
                                      Category.EQUIPMENT])
def test_every_non_mtdc_category_is_caught(category):
    """Not just OTHER — equipment is excluded from MTDC by 200.1 and a fee is
    not a cost. An invoice made only of these has no base either."""
    inv = Invoice("x", "DIG-ENG",
                  lines=(InvoiceLine.of(category, "1000.00"),))
    assert inv.base_is_assessable is False
