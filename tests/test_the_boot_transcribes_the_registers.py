"""The books come back with the deployment, and never over the top of them.

`app/foundation.py` opens the accounts and files the eighteen documents on a
boot, and for the life of the deployment it read **no row** out of any of
them. Replayed against an empty database that is six accounts, eighteen
documents, and nought ledger lines, nought assets, nought invoices — with
every step of `v_audit_walk` reading NO DATA or WAITING. The module's own
docstring said why, and the reason was a category error: *"everything that
is a judgment: the ledger, the classifications, the seal, the rate"*. A
ledger is not a judgment. It is a transcription of a document that same boot
has already filed.

`REGISTERS` is the seven transcriptions a boot can do, and these are the
properties that keep it honest. The one that matters most is the third: a
predicate satisfied by rows a *migration* seeds would make the boot skip a
register nobody has loaded, and the deployment would come back without its
books **silently** — which is `029` in the mechanism written to prevent it.

Every source assertion here was watched failing against the defect restored.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

from app.db import one
from app.foundation import REGISTERS, Register

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
SEED_SH = (SCRIPTS / "seed.sh").read_text()


# ── The list is real ─────────────────────────────────────────────────

def test_every_register_names_a_loader_the_image_ships():
    """`COPY scripts/` puts these in the container. A name that is not there
    is a boot that logs a warning for ever and never loads the register."""
    for r in REGISTERS:
        assert (SCRIPTS / r.script).is_file(), (
            f"{r.name}: scripts/{r.script} is not in the repository, so the "
            f"boot has nothing to run")


def test_every_register_says_what_it_is_for():
    """The floor `actor_portfolio.reason` already has, applied to a loader.
    A register on the boot path with no stated reason is the next person's
    puzzle, and this list is read by somebody deciding whether a new loader
    belongs on it."""
    for r in REGISTERS:
        assert len(r.why) >= 80, f"{r.name}: {len(r.why)} characters of why"


def test_no_register_loader_is_invoked_through_the_api():
    """The line between the two halves, as a property rather than a comment.

    A loader that goes through the API signs in as a person, and
    `refuse_issued_password` means a boot has nobody to be — so over HTTP it
    would fail on every write, or worse, appear to work.

    The rule is about **how the boot invokes it**, not about what the module
    can do. `load_contract_terms.py` has both paths: a person runs it against
    a URL and it records as them, the boot runs it with `--direct` and it
    records as the deployment. So a loader that can reach the API has to be
    invoked with the flag that does not — the first draft of this asserted
    that the module never imports `httpx` at all, which would have forced a
    second copy of the same twenty-six provisions.
    """
    for r in REGISTERS:
        tree = ast.parse((SCRIPTS / r.script).read_text())
        imported = {
            n.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for n in ([a.name for a in node.names]
                      if isinstance(node, ast.Import) else [node.module or ""])
        }
        if "httpx" in imported:
            assert "--direct" in r.args, (
                f"{r.name}: scripts/{r.script} can talk to the API and the "
                f"boot invokes it without --direct, so it will try to sign "
                f"in as somebody — and a boot has nobody to be")


def test_no_register_loader_writes_a_judgment():
    """`tests/test_foundation.py` asks this of `app/foundation.py`'s own SQL,
    and the boot now starts seven other programs — so the fence has to reach
    them or it has stopped meaning anything.

    A boot that classified, sealed, computed a rate or signed one would be
    the machine putting its name on the seal, which is the guarantee the
    whole system rests on.
    """
    forbidden = {"decision", "decision_set", "rate", "rate_certification",
                 "allocation", "labor_certification", "restatement",
                 "position_confirmation", "carve_out"}
    for r in REGISTERS:
        src = (SCRIPTS / r.script).read_text()
        written = set(re.findall(r"(?:INSERT INTO|UPDATE)\s+(\w+)", src))
        assert not written & forbidden, (
            f"{r.name}: scripts/{r.script} writes "
            f"{sorted(written & forbidden)}, which is a judgment with a "
            f"person's name on it and never a transcription")


def test_seed_sh_walks_the_list_rather_than_keeping_one():
    """Two lists of one thing is the defect this module is named after.

    Seven `run` lines stood in `seed.sh` and the boot needed the same seven.
    The list is `REGISTERS`; `seed.sh` calls `scripts/load_registers.py`,
    which walks it. A loader named directly in the shell script again is the
    second list coming back.
    """
    assert "scripts/load_registers.py" in SEED_SH
    for r in REGISTERS:
        assert f"scripts/{r.script}" not in SEED_SH, (
            f"scripts/seed.sh names {r.script} directly as well as walking "
            f"REGISTERS — that is the same list in two places, which is "
            f"exactly what collapsing those seven lines was for")


# ── The list is honest about the database ────────────────────────────

pytestmark_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="reads the live schema; CI sets DATABASE_URL against a bare "
           "Postgres with the migrations applied, which is the population "
           "these assertions are about")


@pytestmark_db
def test_every_predicate_is_real_sql():
    """`tests/test_sql_is_real.py` hands every literal statement to PREPARE
    and finds them by the function they are passed to — these are dataclass
    fields, so that sweep cannot see them. The first draft appended `AS n`
    to each predicate, which `count(*)` does not need and a trailing WHERE
    clause will not take: all seven were unreadable, and the walk correctly
    left all seven alone rather than loading over a live record.

    Through `_rows_in`, which is the thing that runs. The first draft of
    this test composed the same query itself and so passed with the defect
    it is named for restored — it was asserting that *my* SQL was real. That
    is the shape this repository keeps finding, and the only way any of them
    are found is by breaking the code and watching.
    """
    from app.foundation import _rows_in
    for r in REGISTERS:
        assert _rows_in(r) >= 0, r.name


@pytestmark_db
def test_no_predicate_is_satisfied_by_rows_a_migration_seeds():
    """The one that would be expensive to get wrong, and it is silent.

    A migrations-only database has loaded nothing. If a predicate reads
    non-zero there, the boot decides the register is already in, skips the
    loader, and a rebuilt deployment comes back without that register with
    nothing anywhere saying so — an empty set matching an empty set, in the
    mechanism written to stop exactly that.

    `load_awards` is the single exception and carries `always`, because
    `004` seeds one of its four awards as a placeholder and `058` names it,
    so no count on `award` can tell a loaded register from an empty one. It
    is run every time and guards itself.
    """
    if not _is_a_bare_database():
        pytest.skip("this database carries a loaded record, so 'nobody has "
                    "loaded this yet' is not the population under test")
    for r in REGISTERS:
        n = int(one(f"SELECT ({r.loaded}) AS n")["n"])
        if r.always:
            continue
        assert n == 0, (
            f"{r.name}: the predicate reads {n} on a database nothing has "
            f"been loaded into, so the boot would skip the loader and the "
            f"register would never arrive. Give it `always=True` and a "
            f"reason, the way the four awards do, or narrow the predicate")


@pytestmark_db
def test_the_one_that_guards_itself_says_so_and_is_the_only_one():
    """`always` is a permission slip and the list of them can only shrink."""
    guarded = [r for r in REGISTERS if r.always]
    assert [r.name for r in guarded] == ["the four awards"], (
        "a second self-guarding loader is a second register the boot cannot "
        "tell is already in; say why in `why` and change this assertion "
        "deliberately")
    assert "004" in guarded[0].why and "058" in guarded[0].why, (
        "the exception has to name the migrations that make a count useless, "
        "or the next reader cannot check it")


def _is_a_bare_database() -> bool:
    """Whether the migrations are all that has ever run here.

    The assertion above is about a database nothing has been loaded into,
    and against a loaded record every predicate reads non-zero *correctly* —
    so without this it would argue with working code, which is worse than no
    test.

    Read off `evidence` and `ledger_line` rather than off the predicates
    themselves: the predicates are the thing under test, and a guard that
    asked them would skip in exactly the case the test exists for. `evidence`
    is the honest marker because nothing reaches a register before the
    documents are filed — not on a boot, where `ensure_documents()` runs
    first, and not under `scripts/seed.sh`.
    """
    return not any(int(one(f"SELECT count(*) AS n FROM {t}")["n"])
                   for t in ("evidence", "ledger_line"))


@pytestmark_db
def test_only_a_register_that_is_not_in_is_ever_run(monkeypatch):
    """*It never overwrites*, which is the module's first rule, held in one
    place rather than trusted to seven scripts.

    Driven: the walk runs with `subprocess.run` replaced, so nothing is
    loaded and nothing is written, and what it *would* have invoked is
    compared against what the record says is missing. A loader that turns
    out not to be idempotent still cannot reach a record somebody is using,
    because it is not started.

    Asserted against the record rather than against a restatement of the
    condition: the first draft compared the skip rule to itself and could
    not have failed for the thing it names.
    """
    from app import foundation

    missing = {r.script for r in REGISTERS
               if r.always or foundation._rows_in(r) == 0}
    invoked: list[str] = []

    class _Done:
        returncode, stdout, stderr = 0, "", ""

    def fake_run(cmd, **kw):
        invoked.append(Path(cmd[1]).name)
        return _Done()

    monkeypatch.setattr(foundation.subprocess, "run", fake_run)
    foundation.ensure_registers()

    assert set(invoked) == missing, (
        f"the walk started {sorted(set(invoked) - missing)} over a register "
        f"the record already carries, and skipped "
        f"{sorted(missing - set(invoked))} that it does not")


def test_the_dataclass_keeps_the_argv_seed_sh_uses():
    """A loader must not behave one way for a person and another for the
    boot — `args` is the argv and nothing is special-cased. The two that
    take one are the tell."""
    args = {r.script: r.args for r in REGISTERS}
    assert args["read_documents.py"] == ("--write",), (
        "read_documents.py writes nothing without --write, so a boot that "
        "dropped the flag would run it and file nothing")
    assert all(isinstance(r, Register) for r in REGISTERS)


# ── A loader that fails part way through ─────────────────────────────

def test_a_half_loaded_register_is_reported_loudly(monkeypatch, caplog):
    """The next boot will not try again, so this one has to say so.

    A loader that writes some of its rows and then exits non-zero leaves the
    register non-empty — and non-empty is exactly what the skip reads as
    *already in*. So a half-loaded register would be treated as complete for
    ever, silently, which is the worst outcome available to this mechanism:
    a recovered deployment with part of its books and a clean deploy log.

    The first draft reported any non-zero exit as "loaded nothing" without
    looking at the record, which is only true when nothing moved.
    """
    import logging

    from app import foundation

    seen = iter([0, 41])          # empty before, forty-one rows after

    class _Failed:
        returncode, stdout, stderr = 1, "", "parse error on row 42"

    monkeypatch.setattr(foundation, "REGISTERS", REGISTERS[:1])
    monkeypatch.setattr(foundation, "_rows_in", lambda r: next(seen))
    monkeypatch.setattr(foundation.subprocess, "run",
                        lambda cmd, **kw: _Failed())

    with caplog.at_level(logging.INFO, logger="ybi.foundation"):
        assert foundation.ensure_registers() == [], (
            "a loader that exited non-zero must never be reported as a "
            "register this boot transcribed")

    worst = max(r.levelno for r in caplog.records)
    assert worst >= logging.ERROR, (
        "a register left half loaded was logged at "
        f"{logging.getLevelName(worst)}; the next boot skips it, so this is "
        "the one thing in the walk that has to be an error")
    said = caplog.text
    assert "41" in said and "PART WAY" in said and "parse error" in said, (
        "the message has to carry how far it got and what the loader "
        "actually said, or nobody can act on it:\n" + said)


# ── A loader may fill more than one register ─────────────────────────

def test_every_table_a_loader_writes_is_accounted_for():
    """The count has to reach everything the loader puts on the record.

    `load_calendar.py` writes the working calendar, the hours log **and**
    the contractor identities. The first draft of REGISTERS counted
    `work_month` alone: the calendar landed on the boot, the walk called the
    register in, and `contractor_identity` — which needs the ledger, and so
    cannot be written on the pass that loads the calendar — was skipped by
    name for ever after. One test failed on a from-empty seed and nothing
    else said a word.

    So the rule is swept rather than trusted: every table a register loader
    writes has to be named by some register's count. A loader that grows a
    second output fails here until the list catches up.
    """
    named = " ".join(r.loaded for r in REGISTERS)
    for r in REGISTERS:
        if r.always:
            # A loader that runs every time is never skipped, so an output
            # of its that has not landed gets another pass. `load_awards.py`
            # is the one: besides the four awards it links each invoice to
            # the award that authorised it, and the invoice register is
            # loaded by the half a person runs — so that link lands on the
            # pass after it, which is exactly what `always` buys.
            continue
        src = _without_comments((SCRIPTS / r.script).read_text())
        writes = set(re.findall(r"INSERT\s+INTO\s+([a-z_]+)", src))
        writes |= set(re.findall(r"UPDATE\s+([a-z_]+)\b", src))
        writes -= {"audit_log"}          # every writer touches it
        if not writes:
            # A loader whose writes are in the handler it calls rather than
            # in its own SQL. `load_books.py` is the one: it calls
            # `stage_file`, `parse_batch` and `promote_batch`, which is the
            # whole point — one implementation shared with the screen — so
            # there is no SQL here to sweep. The register it fills is counted
            # the same way, and the handler's own writes are swept by
            # `test_sql_is_real.py`.
            assert re.search(r"from app\.routers\.\w+ import", src), (
                f"{r.script} writes nothing this sweep can see and calls no "
                f"handler either, so nothing it does is checked anywhere")
            continue
        for t in sorted(writes):
            assert re.search(rf"\b{t}\b", named), (
                f"scripts/{r.script} writes `{t}` and no register counts it, "
                f"so a boot on which that write does not land will report "
                f"the register in and never try again")


def _without_comments(src: str) -> str:
    """SQL and Python comments out before matching.

    A sentence about a table is not a write to it, and this repository has
    been caught four times asserting over the prose beside the code.
    """
    out = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("--"):
            continue
        out.append(line)
    return "\n".join(out)
