"""The 2025 return is the 2024 one answered, and says which answers are which.

`form_990_field` is the filed return transcribed field by field, and every row
says where its 2025 answer comes from. Four answers — read from the record,
referenced from another line of the return, carried from the filing, or asked
because nobody has answered it — and **the whole value of the document is that
it never prints them alike**. A carried answer that read as a measured one is
how a return gets signed over a figure from last year.

The unit tests here need no database; the rest drive the live views, because
the references are the form's own *must equal* statements and asserting them
against a fixture would be asserting them against my own arithmetic.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from app.domain.form_990_return import (Context, Field, PROVENANCE, Unresolved,
                                        answer, assemble, resolve)

db = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                        reason="needs a database")


def _f(fid, answer_kind, source="", kind="MONEY", prior=""):
    return Field(fid, "I", 10, "1", fid, kind, answer_kind, source, "", prior)


# ── The interpreter, with no database ───────────────────────────────

def _ctx():
    return Context(period="2025",
                   ix={"1": {"total": Decimal("100")},
                       "2": {"total": Decimal("20")},
                       "8b": {"total": Decimal("7")}},
                   viii={"V1": Decimal("50"), "V2": Decimal("5")},
                   x={"X1": Decimal("9")},
                   fn={"x16": Decimal("1000")})


def test_a_part_ix_total_never_counts_the_netted_line():
    """`8b` is the direct expenses of the fundraising event. The form nets it
    against Part VIII line 8a and **excludes it from Part IX**, in the
    instruction at the head of the part. Counting it would overstate expenses
    by the cost of the event and leave the return not cross-footing."""
    c = _ctx()
    assert resolve("ixtotal:total", c) == Decimal("120")
    assert resolve("ix:8b:total", c) == Decimal("7")


def test_a_list_splits_at_the_top_level_only():
    c = _ctx()
    assert resolve("add:viii:V1,viii:V2", c) == Decimal("55")
    assert resolve("add:viii:V1,neg:ix:8b:total", c) == Decimal("43")
    # `sub` takes exactly two, so the second may itself be a list.
    assert resolve("sub:viii:V1,add:viii:V2,ix:2:total", c) == Decimal("25")


def test_a_comma_bearing_source_inside_a_list_is_refused():
    """Silently taking the first fragment would produce a plausible figure,
    and a plausible wrong figure on a tax return is the worst shape there
    is."""
    with pytest.raises(Unresolved):
        resolve("add:ixsum:1,2:total,viii:V1", _ctx())


def test_a_source_nobody_reads_is_refused_rather_than_answered():
    with pytest.raises(Unresolved):
        resolve("whatever:V1", _ctx())
    with pytest.raises(Unresolved):
        resolve("fn:a_thing_the_caller_never_read", _ctx())


def test_a_field_that_refers_to_itself_is_refused():
    c = _ctx()
    c.fields = {"A": _f("A", "field", "field:A")}
    with pytest.raises(Unresolved):
        resolve("field:A", c)


def test_a_carried_answer_is_last_years_and_says_so():
    a = answer(_f("X", "carried", prior="7,685,898"), _ctx())
    assert a.value == "7,685,898"
    assert a.provenance == PROVENANCE["carried"]
    assert "confirm" in a.provenance


def test_an_unanswered_field_is_not_zero_and_not_last_years_answer():
    """*A blank is unanswered, and unanswered is a value.* Printing the 2024
    answer here would be the return asserting something nobody said about
    2025; printing 0.00 would be asserting there is none of it."""
    a = answer(_f("X", "ask", "a count of volunteers nobody keeps",
                  prior="0"), _ctx())
    assert a.value is None
    assert not a.answered
    assert a.says == "a count of volunteers nobody keeps"


# ── Against the record ──────────────────────────────────────────────

def _live():
    from app.db import query
    D = lambda x: Decimal(str(x or 0))
    ix = {r["line_id"]: {"total": D(r["total"]), "program": D(r["program"]),
                         "management": D(r["management"]),
                         "fundraising": D(r["fundraising"])}
          for r in query("SELECT * FROM v_form_990_part_ix WHERE period='2025'")}
    viii = {r["line_id"]: D(r["amount"]) for r in
            query("SELECT * FROM v_form_990_part_viii WHERE period='2025'")}
    px = query("SELECT * FROM v_form_990_part_x WHERE period='2025'")
    x = {r["line_id"]: D(r["amount"]) for r in px}
    x16 = (sum(D(r["amount"]) for r in px
               if r["side"] == "ASSET" and r["line_id"] != "X10b")
           - x.get("X10b", Decimal(0)))
    fields = [Field(r["field_id"], r["part"], r["seq"], r["line_no"],
                    r["label"], r["kind"], r["answer"], r["source"],
                    r["note"], "")
              for r in query("SELECT * FROM form_990_field ORDER BY seq")]
    fn = {"x16": x16,
          "x26": sum(D(r["amount"]) for r in px if r["side"] == "LIABILITY"),
          "x32": sum(D(r["amount"]) for r in px if r["side"] == "EQUITY")}
    # Everything a `fn:` source on the register names. Read here rather than
    # listed, so a new one fails the resolution test below until the script
    # reads it too.
    import re
    for f in fields:
        if f.source.startswith("fn:"):
            fn.setdefault(f.source[3:], 0)
    return fields, Context("2025", ix=ix, viii=viii, x=x, fn=fn)


@db
def test_every_source_on_the_register_resolves():
    """The one that matters. A field whose source nobody reads would print
    blank on a tax return with nothing anywhere saying it had failed — so the
    interpreter raises, and this is what watches it."""
    fields, ctx = _live()
    assert len(fields) > 150, "the register is not loaded on this database"
    assemble(fields, ctx)          # raises Unresolved on the first bad source


@db
def test_the_return_keeps_its_own_must_equal_statements():
    """Part I says *must equal Part VIII, column (A), line 12* and *must equal
    Part IX, column (A), line 25*, and Part XI says *must equal Part X, line
    32*. A replica that did not keep those is not one."""
    fields, ctx = _live()
    a = {x.field.field_id: x.value for x in assemble(fields, ctx)}

    viii_total = sum(ctx.viii.values()) - ctx.ix["8b"]["total"]
    ix_total = sum(v["total"] for k, v in ctx.ix.items() if k != "8b")

    assert a["P1_12"] == viii_total
    assert a["P1_18"] == ix_total
    assert a["P1_19"] == a["P1_12"] - a["P1_18"]
    assert a["P1_22"] == a["P1_20"] - a["P1_21"]
    assert a["P1_13"] + a["P1_14"] + a["P1_15"] + a["P1_16A"] + a["P1_17"] \
        == a["P1_18"], "Part I lines 13 to 17 do not add to line 18"
    assert a["P11_10"] == a["P1_20"] - a["P1_21"]
    assert a["P11_3"] + a["P11_4"] + a["P11_9"] == a["P11_10"], (
        "Part XI does not reconcile, which is the whole of what that part is")


@db
def test_part_x_foots_and_no_account_falls_off_it():
    """A balance sheet that does not balance is not one, and an account on no
    line is money that leaves the return with nothing saying so."""
    from app.db import one
    r = one("SELECT * FROM v_form_990_part_x_check WHERE period = '2025'")
    if not r or r["state"] == "NO DATA":
        pytest.skip("no balance sheet on this database")
    assert r["unmapped"] == 0, r["needs"]
    assert r["variance"] == 0, r["needs"]
    assert r["line_16"] == r["line_26"] + r["line_32"]


@db
def test_every_part_of_the_register_reaches_the_document():
    """The script prints the parts it knows about, and the register is where
    parts are added. A part in one and not the other is a section of the
    return silently missing from the paper — which is the hand-kept map, one
    list wide."""
    import importlib.util
    from pathlib import Path
    from app.db import query
    path = Path(__file__).resolve().parent.parent / "scripts" / "form_990_replica.py"
    spec = importlib.util.spec_from_file_location("replica", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    printed = {k for k, _t, _n in mod.PARTS}
    held = {r["part"] for r in query("SELECT DISTINCT part FROM form_990_field")}
    assert held - printed == set(), (
        f"the register holds parts the document never prints: {held - printed}")


@db
def test_the_document_says_what_it_could_not_answer_and_renders_the_same_twice():
    """Two renders of one record are the same bytes, so a digest that moves
    means a figure moved — `invoice_document.py`'s rule, and the reason the
    publication manifest is worth checking at all."""
    from pypdf import PdfReader
    from io import BytesIO
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "scripts" / "form_990_replica.py"
    spec = importlib.util.spec_from_file_location("replica2", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    import sys
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "a.pdf"
        argv = sys.argv
        try:
            sys.argv = ["x", "--out", str(out)]
            assert mod.main() == 0
            first = out.read_bytes()
            assert mod.main() == 0
            assert out.read_bytes() == first, "the render is not deterministic"
        finally:
            sys.argv = argv

        text = "\n".join(p.extract_text() or ""
                         for p in PdfReader(BytesIO(first)).pages)

    assert "THIS IS NOT A FILED RETURN AND MUST NOT BE FILED" in text, (
        "a reproduction has to say it is one, on the paper")
    assert "carried · confirm" in text, (
        "a carried answer prints as though it were measured")
    assert "What this return does not answer" in text
    # The asked fields print what they need, in the body and in the list.
    assert "needs a count of volunteers" in text
