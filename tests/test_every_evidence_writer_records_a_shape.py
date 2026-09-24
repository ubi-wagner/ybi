"""A document filed by a door that does not read its form is a gap nobody sees.

There are five doors a document can arrive by — the importer's evidence
route, the inbox everybody has, a request reply, a generated invoice and the
boot — and `storage.read_text()` is called at all five because a text layer
read at four of them is missing precisely where somebody later assumes it is
present. The form is the same fact one step along.

So this is `test_storage_paths.py`'s rule pointed at a second column: the
sweep derives the writers from the source rather than keeping a list, and a
sixth door fails here on the day it is written.

And the second test is `029` in the newest place in the system. A family
holding one document agrees with itself perfectly, and a register that
called that UNIFORM would say a parser has been proved against variation
when nothing has ever varied. `NO DATA` is not a milder pass; it is a
different answer, and the difference is the whole value of the register.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Where a document can be written into the register. Derived, not listed:
#: any file under `app/` that inserts an evidence row is a door.
def writers() -> dict[str, str]:
    found = {}
    for path in sorted(ROOT.joinpath("app").rglob("*.py")):
        src = path.read_text()
        if re.search(r"INSERT\s+INTO\s+evidence\b", src, re.I):
            found[str(path.relative_to(ROOT))] = src
    return found


def test_the_sweep_finds_the_doors_it_is_about():
    """A sweep over an empty population is the defect it exists to catch."""
    assert len(writers()) >= 4, (
        "this found almost no evidence writers, which means the pattern "
        "stopped matching rather than that the doors went away")


@pytest.mark.parametrize("path", sorted(writers()))
def test_every_door_that_files_a_document_reads_its_form(path):
    src = writers()[path]
    # Comments out first: a file explaining why it does not do something
    # would otherwise satisfy a test asking whether it does.
    body = re.sub(r"#[^\n]*", "", src)
    assert "record_shape" in body or "record_missing_shape" in body, (
        f"{path} files a document and never calls app.shapes.record_shape. "
        f"Its form is then read only if somebody remembers to run "
        f"scripts/read_shapes.py, which is the shape of defect this "
        f"repository is named after.")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_a_family_of_one_is_no_data_and_never_uniform():
    """One document has not been checked against anything."""
    from app.db import query

    rows = query("SELECT family, instances, state FROM v_document_variability")
    if not rows:
        pytest.skip("no document has been shaped on this record")
    wrong = [r for r in rows if r["instances"] < 2 and r["state"] != "NO DATA"]
    assert not wrong, (
        f"{[r['family'] for r in wrong]} hold a single document and do not "
        f"report NO DATA. A family of one agrees with itself perfectly, and "
        f"calling that UNIFORM reads as 'this parser has been proved against "
        f"variation' where the truth is that nothing has ever varied.")
    # And the other direction, so the state cannot become a constant.
    plural = [r for r in rows if r["instances"] >= 2]
    if plural:
        assert all(r["state"] in ("VARIES", "UNIFORM") for r in plural), (
            "a family holding more than one document still reports NO DATA, "
            "so the register cannot distinguish 'not measured' from "
            "'measured and the same'")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_the_register_names_what_differs_rather_than_scoring_it():
    """A variability index is a figure nobody can act on.

    `varies_on` has to carry the attribute names, because what a person does
    with this register is go and look at the attribute — the same reason a
    reconciling item carries the lines behind it instead of a plug.
    """
    from app.db import query

    rows = query("""SELECT family, varies_on, values FROM v_document_variability
                     WHERE state = 'VARIES'""")
    if not rows:
        pytest.skip("nothing on this record varies")
    for r in rows:
        assert r["varies_on"], (
            f"{r['family']} reports VARIES and names no attribute, which "
            f"tells a reader that something is different and not what")
        assert set(r["varies_on"]) <= set(r["values"]), (
            f"{r['family']} names attributes it carries no values for")
