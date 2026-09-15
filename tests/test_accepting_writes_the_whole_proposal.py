"""Accepting a recommendation writes every field the proposal carried.

`accept` built each register's input model by naming its fields, and dropped
four of `UnitIn`'s — `months_occupied`, `actual_annual_charge`,
`market_rate_psf` and `market_basis` — and four of `FacilityIn`'s. So a
recommendation carrying a tenancy that ran five months was written as twelve,
which weights the 200.465 carve-out; and every rent and market rate a
proposal carried was discarded, so the subsidy the facilities screen exists to
measure read `0.00` on a building with $237,081.48 of rent against it.

Nothing refused it and nothing could. The schema validates the **proposal**,
which was complete; what reached the register was a subset of it. It is the
hand-kept map one layer below the places `CLAUDE.md` already names it — and
it was found by looking at the screen, not by a test.

So the rule is the property rather than a list: **every field of each
register's input model is reachable from the merged proposal.** A field added
to `UnitIn` next year is covered without anybody remembering this file.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The fields `accept` supplies itself rather than reading off the proposal —
#: the subject's own id, and the three places it stamps the controller's
#: citation and rationale onto the row rather than the recommender's.
SUPPLIED = {"facility_id", "unit_id", "asset_id", "note", "source_document",
            "market_source"}


def test_every_register_field_is_reachable_from_a_proposal():
    from app.routers.facilities import AssetFundingIn, FacilityIn, UnitIn
    from app.routers.positions import _as

    for model in (FacilityIn, UnitIn, AssetFundingIn):
        # A proposal naming every field of the model must produce a model
        # carrying every one of them. `_as` filters to the model's own fields,
        # so this fails the moment it goes back to naming them by hand.
        sample = {name: _a_value(f) for name, f in model.model_fields.items()}
        built = _as(model, sample)
        for name in model.model_fields:
            if name in SUPPLIED:
                continue
            assert getattr(built, name) == sample[name], (
                f"{model.__name__}.{name} did not survive the merge — "
                f"accepting a recommendation would drop it")


def _a_value(field):
    """A value of the field's own type, so the model validates it."""
    t = str(field.annotation)
    if "SpaceUse" in t:
        return "TENANT"
    if "OccupancyStatus" in t:
        return "OCCUPIED"
    if "FundingKind" in t:
        return "FEDERAL"
    if "bool" in t:
        return True
    if "float" in t or "int" in t:
        return 7.0
    return "x" * 12


def test_accept_does_not_name_a_register_s_fields_by_hand():
    """The rule, in the code that ships. Asserted on the parsed source rather
    than on a spelling: a `FacilityIn(...)` call with keyword after keyword is
    exactly the shape that lost four fields, and it reads as careful."""
    src = (ROOT / "app" / "routers" / "positions.py").read_text()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "accept")
    for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
        name = getattr(call.func, "id", "")
        if name in {"FacilityIn", "UnitIn", "AssetFundingIn"}:
            raise AssertionError(
                f"{name} is constructed field by field in accept(). Build it "
                f"from the merged proposal with `_as` instead, or the next "
                f"field added to it is dropped silently.")
