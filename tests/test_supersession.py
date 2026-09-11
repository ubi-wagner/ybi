"""What supersession broke, three times, in the same shape.

Reclassifying leaves the old `decision_line` in place with `live = false` —
that is how the record stays append-only. Any query that reaches
`decision_line` *from the ledger side* and does not say `dl.live` then joins
a line once per judgment it has ever carried, and every sum multiplies.

It was latent for as long as nothing could supersede, which is why three
places had it and none of them was wrong when it was written:

  v_classification_coverage   classified doubled on one reclassification,
                              and the *scope* grew — the tell, because no
                              judgment changes how much there is to judge
  the classification queue    a group judged four times printed four times
                              its amount, on the screen the engagement is
                              worked from
  v_form_990_functional       a reclassified line landed in its function
                              *and* in NOT_YET_CLASSIFIED, so a tax return
                              would carry the same cost twice and the extra
                              would have looked like work remaining

So this sweeps rather than naming them. A fourth one will be caught by a test
instead of by somebody reading a number that looks slightly high.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "app" / "sql"
APP = ROOT / "app"

#: A view's own text, and nothing of the next one's.
#:
#: The first version of this matched `CREATE VIEW (\w+) AS(.*?);` and let a
#: body run into whatever followed when there was no COMMENT between them, so
#: it reported offences against views that did not contain the offending line.
#: A test that names the wrong file is worse than no test: somebody edits the
#: innocent one and the real defect stays.
def _definitions() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for path in sorted(SQL.glob("*.sql")):
        src = path.read_text()
        marks = [(m.start(), m.group(1)) for m in
                 re.finditer(r"CREATE (?:OR REPLACE )?VIEW (\w+) AS", src)]
        for i, (start, name) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(src)
            out.append((name, src[start:end]))
    return out


def _latest_definition(view: str) -> str | None:
    """A migration is never edited once applied, so the superseded text stays
    on disk. The last definition in filename order is the one in force."""
    found = None
    for name, body in _definitions():
        if name == view:
            found = body
    return found


def _views_joining_decision_line() -> dict[str, str]:
    names = {n for n, body in _definitions() if "decision_line" in body}
    return {n: _latest_definition(n) for n in sorted(names)}


#: A join, and enough of what follows to see a condition on the next line.
#: The handler check first looked only at the rest of the same line and
#: reported a join whose `AND dl.live` had been wrapped.
JOIN = re.compile(
    r"decision_line\s+(\w+)\s+ON\s+\w+\.line_id\s*=\s*\w+\.line_id")


def _unfiltered(body: str) -> list[str]:
    out = []
    for m in JOIN.finditer(body):
        alias = m.group(1)
        window = body[m.end():m.end() + 160]
        # Stop at the next join or the WHERE: a `dl.live` belonging to some
        # later clause is not this join's filter.
        window = re.split(r"\bJOIN\b|\bWHERE\b|\bGROUP\b", window)[0]
        if f"{alias}.live" not in window:
            out.append(alias)
    return out


def test_no_view_joins_decision_line_by_line_without_filtering_live():
    offenders = []
    for name, body in _views_joining_decision_line().items():
        if not body:
            continue
        for alias in _unfiltered(body):
            offenders.append(f"{name} (alias {alias})")
    assert not offenders, (
        "these join decision_line by line_id without `AND <alias>.live`, so a "
        "reclassified line is counted once per judgment it has ever carried: "
        + ", ".join(offenders))


def test_no_handler_joins_decision_line_by_line_without_filtering_live():
    """The classification queue had it in Python rather than in a view, and a
    group judged four times printed four times its amount."""
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        src = path.read_text()
        for m in JOIN.finditer(src):
            alias = m.group(1)
            window = re.split(r"\bJOIN\b|\bWHERE\b|\bGROUP\b",
                              src[m.end():m.end() + 160])[0]
            if f"{alias}.live" not in window:
                line = src[:m.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(ROOT)}:{line}")
    assert not offenders, (
        "these join decision_line by line_id without filtering live: "
        + ", ".join(offenders))


def test_reclassifying_reverses_rather_than_stacking():
    """The other half. If a second judgment did not reverse the first, there
    would be two live decisions and the dead-row problem would become a
    live-row problem, which no filter can fix."""
    src = (ROOT / "app" / "routers" / "classify.py").read_text()
    m = re.search(r"def decide\(.*?\n(?=\n@router)", src, re.S)
    assert m
    assert "reversed_at = now()" in m.group(0)


def test_the_live_flag_is_kept_in_step_by_the_schema():
    """`decision_line.live` is maintained by a trigger on `decision`, not by
    application code. Every query above trusts it, so it has to hold when a
    handler is wrong."""
    joined = "\n".join(p.read_text() for p in sorted(SQL.glob("*.sql")))
    assert "decision_line_live_sync" in joined, (
        "the trigger that flips decision_line.live when a decision is "
        "reversed is gone; every dl.live filter in the system now trusts a "
        "column nothing maintains")
