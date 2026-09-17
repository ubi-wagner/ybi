"""A reply lands on the register, or the preview says it will not.

A key changed under a workbook that was already out. `085` made the
register's key `FA-<gl account>-<system>` — system number 165 is two assets
in two accounts, and keying on the system number alone had already lost one
of them. A workbook issued before that carries `FA-162` against a register
holding `FA-1501-162`, so **not one of its 262 ids matches**: that is a real
reply, 263 rows, every one answered.

Nothing was wrong with the form when it went out, which is the point — a
register may be re-keyed for a good reason while an ask sits in somebody's
inbox. What was wrong is what happened next. `_write_assets` upserts on
`asset_id`, so a key that never collides **inserts**: accepting would have
written 263 new assets beside the 263 on file and doubled a $23,419,573.64
basis. The only thing that could have said so in advance is `lands_on`,
which `084` built for the space form for exactly this reason — *a name the
register does not hold invents one, so it ties by construction and says
nothing at all* — and which was never extended to assets.

Every driven assertion here was watched failing against the defect restored.
The pre-fill one is a source assertion and says so: it is about which source
is consulted first, which is not observable from the outside on a record
where the two agree.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

from app.routers import requests as R

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="reads the live register; CI sets DATABASE_URL against a bare "
           "Postgres with the migrations applied")


@dataclass
class _Row:
    number: int
    values: dict

    @property
    def usable(self):
        return True


class _Filled:
    def __init__(self, rows):
        self.rows = rows

    @property
    def usable(self):
        return self.rows


def _asset_on_the_record():
    rows = R.query("""SELECT asset_id, gl_account FROM asset
                       WHERE period = '2025' AND gl_account <> ''
                       ORDER BY asset_id LIMIT 1""")
    if not rows:
        pytest.skip("no asset register on this database")
    return rows[0]


# ── The key that goes out is the key that comes back ──────────────────

def test_the_workbook_is_pre_filled_from_the_register():
    """Not from the parser, which describes the source document rather than
    the record and parts company with it the moment anybody corrects an
    asset.

    **A source assertion, deliberately.** The first draft asserted that the
    pre-filled ids are the register's, and passed with the register read
    deleted — because on this record the parser produces the same keys, so
    the two are indistinguishable from the outside. A test that cannot fail
    for the thing it names is the defect this repository keeps finding, and
    the honest fix was to assert the thing that is actually different: which
    source is read first.
    """
    import inspect
    src = inspect.getsource(R._known_rows)
    body = src[src.index('form.name == "ASSET_REGISTER"'):]
    body = "\n".join(l for l in body.splitlines()
                     if not l.lstrip().startswith("#"))
    register = body.index("FROM asset")
    parser = body.index("_asset_schedule(")
    assert register < parser, (
        "the asset workbook is pre-filled from the parsed schedule before "
        "the register, so it describes the document rather than the record")

    # And the register's own ids are what a person gets.
    a = _asset_on_the_record()
    ids = {r.get("asset_id")
           for r in R._known_rows(R._form("ASSET_REGISTER"), "2025")}
    assert a["asset_id"] in ids


def test_a_row_carrying_the_register_key_lands_on_that_asset():
    a = _asset_on_the_record()
    filled = _Filled([_Row(3, {"asset_id": a["asset_id"],
                               "gl_account": a["gl_account"]})])
    assert R._asset_keys("2025", filled) == {3: (a["asset_id"], "on")}


def test_a_row_carrying_the_schedules_own_id_is_resolved_by_its_account():
    """The reply already out there. It is a rule and not a guess: the account
    is a column the reply carries and the reconstruction is exactly the key
    `load_assets.py` builds."""
    a = _asset_on_the_record()
    gl = a["gl_account"]
    bare = a["asset_id"].removeprefix(f"FA-{gl}-")
    if bare == a["asset_id"]:
        pytest.skip(f"{a['asset_id']} is not keyed FA-<account>-<id>")
    filled = _Filled([_Row(3, {"asset_id": f"FA-{bare}", "gl_account": gl})])
    assert R._asset_keys("2025", filled) == {3: (a["asset_id"], "by account")}


def test_a_row_naming_no_asset_is_new_and_says_so():
    """Creating is legitimate — the form's fallback asks somebody to replace
    a balance-sheet total with the assets under it — so this is not refused.
    It is *reported*, which is the whole point of the panel."""
    filled = _Filled([_Row(3, {"asset_id": "FA-NOT-A-REAL-ASSET",
                               "gl_account": "9999"})])
    assert R._asset_keys("2025", filled) == {3: ("FA-NOT-A-REAL-ASSET", "new")}
    panel = R._asset_lands_on("2025", filled)
    assert [p["how"] for p in panel] == ["new"], panel
    assert panel[0]["rows"] == 1


def test_an_id_with_no_account_is_never_resolved():
    """More than one candidate means no candidate, and no candidate at all is
    the same answer. Without the account there is nothing to reconstruct the
    key from, and guessing between assets is what `085` was about."""
    a = _asset_on_the_record()
    bare = a["asset_id"].removeprefix(f"FA-{a['gl_account']}-")
    if bare == a["asset_id"]:
        pytest.skip(f"{a['asset_id']} is not keyed FA-<account>-<id>")
    filled = _Filled([_Row(3, {"asset_id": f"FA-{bare}", "gl_account": ""})])
    assert R._asset_keys("2025", filled)[3][1] == "new"


def test_the_panel_and_the_writer_read_the_same_resolver():
    """`subject_merged()`'s rule: a panel that says what will happen and a
    writer that does something else is worse than no panel. Asserted on the
    source, because the two are different functions and only one of them can
    be driven without writing."""
    import inspect
    for fn in (R._asset_lands_on, R._write_assets):
        src = inspect.getsource(fn)
        assert "_asset_keys(" in src, (
            f"{fn.__name__} does not read _asset_keys, so the preview and "
            f"the write can disagree about which asset a row is")
