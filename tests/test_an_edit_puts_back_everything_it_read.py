"""A form that corrects a row has to read back every column it writes.

`put_unit` is a full upsert, so the space form writes every column it holds
whether the person touched it or not. Pre-filling that form from the rent
roll is what makes a correction possible at all — the register could be
corrected from the day it was written, by retyping an identifier exactly,
which is not a thing anybody does — and it is only safe while the rent roll
carries every one of those columns. It did not: `floor` and `market_source`
were absent, so the first edit would have cleared both without a word.

That is `084`'s merge defect from the other end. There the trigger validated
a proposal rather than the row that would be written; here the screen would
have written a row from a partial read. Both are checking, or filling in,
something other than what actually lands.

The list is derived from the form and from `information_schema`, so a field
added to either side is covered without anybody remembering this file.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

SCREEN = Path(__file__).resolve().parents[1] / "web/src/pages/Facilities.jsx"

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")


def fields_the_form_writes() -> set[str]:
    """The keys `SpaceForm` holds in its state, which is what `save()` spreads
    into the request. Read from the initial state rather than from the inputs,
    because a key with no input of its own — `floor` was one — is still
    written, and is exactly the kind that gets cleared silently."""
    src = SCREEN.read_text()
    body = src[src.index("function SpaceForm("):]
    start = body.index("useState({")
    depth, i = 0, start + len("useState(")
    while True:                                   # find the object's own close
        if body[i] == "{":
            depth += 1
        elif body[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    literal = body[start:i]
    return set(re.findall(r"(\w+):", literal))


def test_every_field_the_space_form_writes_is_on_the_rent_roll():
    from app.db import query
    have = {r["column_name"] for r in query(
        """SELECT column_name FROM information_schema.columns
            WHERE table_name = 'v_space_economics'""")}
    writes = fields_the_form_writes()
    assert writes, "could not read the form's state"
    missing = sorted(writes - have)
    assert not missing, (
        f"the space form writes {missing} and the rent roll does not carry "
        "them, so pre-filling an edit from it would write them back empty")


def test_the_form_can_be_handed_a_room_to_correct():
    """Behaviour, not prose: the component takes `editing` and fills from it.

    Asserted on what runs — the parameter and the state it sets — rather than
    on a comment beside it, which is the defect this repository has shipped
    five times.
    """
    src = re.sub(r"/\*.*?\*/", "", SCREEN.read_text(), flags=re.S)
    src = re.sub(r"//.*", "", src)
    body = src[src.index("function SpaceForm("):]
    assert re.search(r"function SpaceForm\(\{[^}]*\bediting\b", body)
    assert "setOpen(true)" in body[body.index("editing"):]


def test_a_null_from_the_register_is_a_blank_and_not_a_refusal():
    """The other half: what the read produced has to be postable.

    `facility.code` is nullable, `FacilityIn.code` is `str = ""`, and a
    default does not accept `None` — so posting a row back exactly as the API
    answered with it was a 422 naming a field nobody had typed in. The
    screens coerce with `|| ""` and were right by luck; `BlankNotNull` makes
    it the rule, so a correction is a round trip rather than a re-entry.
    """
    from app.routers.facilities import FacilityIn, UnitIn

    facility = FacilityIn(**{
        "facility_id": "T", "name": "T", "usable_sqft": 1,
        # every string field, as the register answers when it holds nothing
        "code": None, "address": None, "landlord": None,
        "market_basis": None, "source_document": None, "note": None})
    for f in ("code", "address", "landlord", "market_basis",
              "source_document", "note"):
        assert getattr(facility, f) == "", f"{f} should read blank, not None"

    unit = UnitIn(**{
        "unit_id": "U", "facility_id": "T", "label": "U", "usable_sqft": 1,
        "use": "VACANT", "status": "VACANT",
        "floor": None, "occupant": None, "market_basis": None,
        "market_source": None, "note": None})
    for f in ("floor", "occupant", "market_basis", "market_source", "note"):
        assert getattr(unit, f) == "", f"{f} should read blank, not None"


def test_it_does_not_blank_a_field_that_may_be_absent():
    """A nullable non-string keeps its None — `year_built` unknown is not 0."""
    from app.routers.facilities import FacilityIn
    f = FacilityIn(facility_id="T", name="T", usable_sqft=1,
                   year_built=None, rentable_sqft=None, market_rate_psf=None)
    assert f.year_built is None and f.rentable_sqft is None
    assert f.market_rate_psf is None
