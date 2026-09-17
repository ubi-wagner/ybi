"""Tom's signature on the rate, and what it does and does not block.

Everything up to the rate is free-order: fill in, classify, upload, seal, in
whatever order the work arrives. **Nothing downstream is blocked** — an invoice
can be regenerated and a workbook produced at any time, because testing and
evaluating the system is ordinary work and a machine that refused it is one
people route around. What changes is whether the paper says it is certified.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "app" / "sql" / "082_tom_certifies_the_rate.sql"
RATES = ROOT / "app" / "routers" / "rates.py"
INVOICE = ROOT / "app" / "domain" / "invoice_document.py"


def _code(path: Path, func: str) -> str:
    """One function's source with its docstring and comments removed.

    Every test in this file that reads a handler needs this: the handlers here
    explain in prose exactly what they must not do, so a raw-text assertion
    reads the explanation and answers with it.
    """
    import ast

    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func:
            body_ = node.body
            if (body_ and isinstance(body_[0], ast.Expr)
                    and isinstance(body_[0].value, ast.Constant)
                    and isinstance(body_[0].value.value, str)):
                body_ = body_[1:]          # drop the docstring
            return "\n".join(ast.unparse(n) for n in body_)
    raise AssertionError(f"{func}() is gone from {path.name}")


def body() -> str:
    return re.sub(r"--[^\n]*", "", MIGRATION.read_text())


def test_certification_is_not_the_sponsor_conversation():
    """`rate.status` is PROPOSED/ACCEPTED — whether NCDMM has answered.

    Certification is the other axis: the controller asserting the rate is
    final and his. Overloading one word with both leaves a reviewer unable to
    tell a position the organisation has taken from a signature on its own
    arithmetic, which is what `062` refused to do to `PROPOSED`.
    """
    assert "CREATE TABLE rate_certification" in body(), (
        "the certification register is gone")
    # Code, not prose. The handler's own docstring explains that this is not
    # `rate.status`, so reading the raw text failed against a function that
    # obeys the rule perfectly — a test arguing with correct code, which is
    # the same root cause as one that passes over a defect: asserting over
    # words rather than over what runs.
    assert "rate.status" not in _code(RATES, "certify"), (
        "certifying touches rate.status, which is the sponsor conversation "
        "and not a signature")
    assert "UPDATE rate " not in _code(RATES, "certify"), (
        "certifying updates the rate rows themselves")


def test_a_signature_names_the_rates_it_is_on():
    """Not just the seal.

    Found by driving it: unseal, re-seal identical judgments, recompute — the
    seal hash is a function of the judgments so it comes back the same, and
    the signature revived on its own. `POST /rates/compute` takes
    `admin_labour`, so the same seal yields 34.82% or 43.99%; the revived
    signature would have been on a rate nobody signed.
    """
    assert "CREATE TABLE rate_certification_line" in body(), (
        "the certificate no longer names the rate rows it covers, so a "
        "recompute cannot kill it")
    assert "certification_covers_a_rate" in body(), (
        "a certificate with no lines is a signature on nothing and nothing "
        "refuses it")


def test_nothing_downstream_is_blocked_by_an_unsigned_rate():
    """The design is a label, not a gate.

    A renderer or a route that refused to produce output without a signature
    would make the system unusable for the thing it is used for most —
    testing and evaluating against real figures.
    """
    for path in (ROOT / "app" / "routers" / "reports.py",
                 ROOT / "app" / "routers" / "restate.py"):
        if not path.exists():
            continue
        src = path.read_text()
        assert "require_certified" not in src, (
            f"{path.name} gates on certification. Nothing downstream is "
            f"blocked — uncertified output carries NOT CERTIFIED instead.")


def test_the_invoice_says_which_it_is_in_both_directions():
    """A document silent about certification leaves the reader to assume, and
    the assumption made about a figure on a letterhead is the generous one."""
    src = INVOICE.read_text()
    assert "def _certification(" in src, "the invoice has no certification band"
    fn = src[src.index("def _certification("):src.index("def _page_number(")]
    assert "NOT CERTIFIED" in fn, "the uncertified band no longer says so"
    assert "if doc.certified:" in fn, (
        "the band no longer prints anything when the rate IS certified, so a "
        "reader cannot tell a certified document from one that never asked")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_every_period_gets_a_row_and_a_reason():
    """"No certificate" and "no period" are different facts."""
    from app.db import query

    rows = query("SELECT period, certified, why_not FROM v_rate_certified")
    assert rows, "v_rate_certified answers nothing at all"
    for r in rows:
        if r["certified"]:
            assert r["why_not"] is None, (
                f"{r['period']} is certified and still carries a reason why not")
        else:
            assert (r["why_not"] or "").strip(), (
                f"{r['period']} is not certified and does not say why, which "
                f"is the dead end this system keeps finding")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_the_certificate_does_not_list_the_act_that_makes_it():
    """The certification step is necessarily open when the snapshot is read.

    Listing it put "The rate certified — open" on the face of the certificate,
    which is a document contradicting itself. Excluded by key rather than by
    number, because the sequence has been renumbered once already and a
    literal would have followed it silently.
    """
    fn = _code(RATES, "certify")
    assert "key <> 'CERTIFY'" in fn, (
        "the certificate lists the act that creates it")
    assert not re.search(r"seq\s*<>\s*9", fn), (
        "the step is excluded by its number, which the renumbering in 082 "
        "shows is not stable")
