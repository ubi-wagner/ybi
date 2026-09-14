"""Rendering an invoice onto the face it was issued on.

The America Makes invoices are the template and the middle is the part that
moves. These hold the things that would be quietly wrong otherwise: the
arithmetic on the face, what happens when there are more lines than a page,
and the one rule that keeps a reproduction from becoming a forgery.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.invoice_document import (CATEGORY_LABEL, DocumentLine,
                                         InvoiceDocument, Party, render)

ROOT = Path(__file__).resolve().parent.parent

REMIT = Party("Youngstown Business Incubator",
              "241 West Federal Street\nYoungstown, OH 44503",
              "UEI E38PN6F4AVU3 · CAGE 5EAR9")
BILL = Party("NCDMM - America Makes", "236 W Boardman Street\nYoungstown, OH 44503")


def _doc(lines, **kw) -> InvoiceDocument:
    base = dict(number="10018", invoice_date=date(2026, 5, 1),
                remit_to=REMIT, bill_to=BILL, lines=tuple(lines))
    base.update(kw)
    return InvoiceDocument(**base)


#: Invoice 10018 exactly as transcribed from YBI_Invoices_1.pdf. The register
#: and the renderer are held to the same figures the domain tests use, so the
#: three cannot drift apart.
DRIVE_AM = [
    DocumentLine("LABOR", Decimal("18448.11"), "DRIVE AM Project - April 2026",
                 personnel="Engel, Gaffney, Kale, Negro, Jaric"),
    DocumentLine("TRAVEL", Decimal("0.00")),
    DocumentLine("MATERIALS", Decimal("0.00")),
    DocumentLine("CONSULTANT", Decimal("0.00")),
    DocumentLine("ODC", Decimal("19145.79")),
]


def test_the_lines_foot_to_the_invoice():
    doc = _doc(DRIVE_AM, total=Decimal("37593.90"))
    assert doc.footing == Decimal("37593.90")


def test_the_header_total_is_not_re_derived_from_the_lines():
    """If they ever disagree the invoice has to be able to say so.

    Recomputing the total from the lines would make that impossible: the two
    would agree by construction and an invoice that does not foot would print
    as though it did. The deferred trigger in the schema should make this
    unreachable; the renderer still refuses to paper over it.
    """
    doc = _doc(DRIVE_AM, total=Decimal("40000.00"))
    assert doc.total == Decimal("40000.00")
    assert doc.footing == Decimal("37593.90")
    body = render(doc)
    assert b"%PDF" in body[:8]


def test_a_reproduction_says_it_is_one():
    """An invoice already issued has a document of record and it is not this
    one. Printing the same face without saying so puts a second artefact into
    circulation that a reader cannot tell from the first."""
    from pypdf import PdfReader
    from io import BytesIO

    issued = _doc(DRIVE_AM, total=Decimal("37593.90"), status="ISSUED",
                  source_document="YBI_Invoices_1.pdf", is_original=False)
    text = PdfReader(BytesIO(render(issued))).pages[0].extract_text()
    assert "NOT THE DOCUMENT OF RECORD" in text
    assert "YBI_Invoices_1.pdf" in text


def test_an_invoice_this_organisation_is_issuing_carries_no_such_band():
    from pypdf import PdfReader
    from io import BytesIO

    draft = _doc(DRIVE_AM, total=Decimal("37593.90"), status="DRAFT",
                 is_original=True)
    text = PdfReader(BytesIO(render(draft))).pages[0].extract_text()
    assert "NOT THE DOCUMENT OF RECORD" not in text


def test_the_middle_expands_and_the_total_lands_on_the_last_page():
    """The fixed part is fixed and the table is the part that moves.

    A total stranded on a page of its own, or a row split across a page
    break, is how an invoice stops being readable at exactly the moment it
    has enough lines to need reading.
    """
    from pypdf import PdfReader
    from io import BytesIO

    many = [DocumentLine("LABOR", Decimal("100.00"), f"Task order {i}")
            for i in range(60)]
    doc = _doc(many, number="10101", total=Decimal("6000.00"), is_original=True)
    reader = PdfReader(BytesIO(render(doc)))
    assert len(reader.pages) > 1, "sixty lines should not fit on one page"

    pages = [p.extract_text() for p in reader.pages]
    assert "TOTAL DUE" in pages[-1], "the total belongs on the last page"
    assert sum("TOTAL DUE" in p for p in pages) == 1, "one total, once"
    for p in pages[:-1]:
        assert "continued" in p, "a page that carries on has to say so"
    # Every line reaches the paper. A row lost at a page break is the failure
    # nobody notices, because the invoice still looks complete.
    text = "\n".join(pages)
    for i in range(60):
        assert f"Task order {i}" in text, f"line {i} never printed"


def test_every_page_knows_how_many_there_are():
    from pypdf import PdfReader
    from io import BytesIO

    many = [DocumentLine("ODC", Decimal("100.00"), f"Item {i}") for i in range(60)]
    doc = _doc(many, number="10101", total=Decimal("6000.00"), is_original=True)
    reader = PdfReader(BytesIO(render(doc)))
    n = len(reader.pages)
    for i, page in enumerate(reader.pages, start=1):
        assert f"Page {i} of {n}" in page.extract_text(), (
            f"page {i} does not say it is page {i} of {n}; a reader cannot "
            f"tell whether they have the whole invoice")


def test_rendering_is_deterministic():
    """Two renders of the same invoice are the same bytes.

    The filing route content-addresses what it renders. Without this every
    press of the button files another copy that differs only in a timestamp
    reportlab stamped inside it, and the evidence volume fills with documents
    nobody can tell apart.
    """
    doc = _doc(DRIVE_AM, total=Decimal("37593.90"))
    assert render(doc) == render(doc)


def test_a_long_description_wraps_instead_of_running_into_the_figures():
    from pypdf import PdfReader
    from io import BytesIO

    long = ("A scope line long enough that it cannot possibly fit inside the "
            "description column and must therefore wrap onto further rows "
            "rather than running underneath the quantity and rate figures")
    doc = _doc([DocumentLine("LABOR", Decimal("1.00"), long)],
               total=Decimal("1.00"), is_original=True)
    text = PdfReader(BytesIO(render(doc))).pages[0].extract_text()
    # Every word survives the wrap, which is what distinguishes wrapping from
    # truncating.
    for word in long.split():
        assert word in text


def test_an_unmapped_category_prints_as_itself():
    """A category nobody thought about should be visible on the invoice, not
    silently unlabelled."""
    line = DocumentLine("SOMETHING_NEW", Decimal("5.00"))
    assert line.label == "SOMETHING_NEW"
    assert "SOMETHING_NEW" not in CATEGORY_LABEL


def test_every_category_the_register_can_hold_has_a_word_for_it():
    """`invoice_category` is an enum in the schema. A value it allows and the
    renderer has no label for would print as an identifier on a document that
    goes to a sponsor."""
    sql = (ROOT / "app" / "sql" / "010_invoices.sql").read_text()
    m = re.search(r"CREATE TYPE invoice_category AS ENUM \((.*?)\);", sql, re.S)
    assert m, "invoice_category is gone"
    for value in re.findall(r"'(\w+)'", m.group(1)):
        assert value in CATEGORY_LABEL, (
            f"the register can record category {value!r} and the invoice has "
            f"no word to print for it")


def test_a_line_at_zero_still_prints():
    """The zero lines are the contract's allowable categories, not noise.

    Invoice 10018 carries TRAVEL 0.00, MATERIALS 0.00 and CONSULTANT 0.00 in
    a month when none were spent, because these invoices list what the award
    *funds* rather than what had activity — Drive AM's Schedule B funds
    exactly those five categories and the invoice shows exactly those five.

    Dropping an empty row would produce a tidier document that says something
    different: that the category was unavailable, when it was available and
    unused. And a renderer willing to filter empty rows is one step from
    filtering the absence that matters most — this invoice has no indirect
    line because Schedule B has none.
    """
    from pypdf import PdfReader
    from io import BytesIO

    doc = _doc(DRIVE_AM, total=Decimal("37593.90"), is_original=True)
    text = PdfReader(BytesIO(render(doc))).pages[0].extract_text()

    for label in ("Travel", "Materials", "Consultant"):
        assert label in text, (
            f"the {label} line was dropped because it is zero. It is a "
            f"category the contract allows with no cost this period, and the "
            f"invoice lists what the award funds.")
    assert text.count("0.00") >= 3, "the zero amounts themselves are gone"

    # Every line recorded reaches the paper, whatever it is worth.
    assert len(doc.lines) == 5
