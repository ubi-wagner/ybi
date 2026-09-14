"""One judgment, many lines — and the system says which.

Classifying a group of forty-five lines records **one** decision with a
scope, not forty-five. That is the design: a scope is an account and a payee,
and the judgment covers every line in it. `one_live_decision_per_unit` is
what makes it safe, and the handler proves its lines landed rather than
assuming.

From the outside it is indistinguishable from a judgment that reached one
line. The system review's proportion check could not tell the difference, and
neither can a person reading "Recorded" after judging $1.2m across thirteen
lines — or an auditor reading two hundred decisions against five thousand
ledger lines, which looks like coverage and is not.

So the count is said out loud in both places a person meets it: the response
the queue shows, and the workpaper that leaves the building.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSIFY = (ROOT / "app" / "routers" / "classify.py").read_text()
QUEUE = (ROOT / "web" / "src" / "pages" / "ClassifyQueue.jsx").read_text()


def decide_body() -> str:
    body = CLASSIFY[CLASSIFY.index("def decide("):]
    return body[:body.index("\n@router")]


def test_the_response_says_how_many_lines_it_covered():
    body = decide_body()
    assert '"lines":' in body and '"amount":' in body, (
        "decide() reports how many decisions it created and not what they "
        "covered, so 'decisions_created: 1' reads the same for one line and "
        "for four hundred")


def test_the_count_is_the_one_that_was_proved_to_land():
    """Not `len(with_lines)` — the number the handler counted back out of
    `decision_line`.

    ON CONFLICT DO NOTHING is how a judgment with no lines at all was
    reported as `decisions_created: 1`. The count that goes in the response
    has to be the one that survived that check, or the response is an
    assumption again.
    """
    body = decide_body()
    assert "lines_covered += attached" in body, (
        "the reported line count is not the one read back from decision_line "
        "after the insert")


def test_the_amount_is_money():
    """Floats in a cost model produce variances that take hours to chase."""
    body = decide_body()
    assert "money(amount_covered)" in body


def test_the_queue_says_it_to_the_person_who_pressed_the_key():
    assert "got?.lines" in QUEUE and "line${got.lines === 1" in QUEUE, (
        "the classification queue records a judgment and does not say what "
        "it covered")


def test_the_queue_says_when_it_replaced_something():
    """`decisions_created: 1` read the same whether a group was judged for
    the first time or rejudged."""
    assert "got?.superseded" in QUEUE


def test_the_workpaper_says_it_too():
    """A workbook travels, and the caveat has to travel with it.

    Two hundred decisions against five thousand ledger lines reads as
    coverage to somebody who has not been told otherwise.
    """
    import app.domain.package as package
    src = inspect.getsource(package.build_package)
    assert "Ledger lines those decisions cover" in src, (
        "the audit package's index gives a decision count with nothing to "
        "read it against")
    assert "not one per ledger line" in src, (
        "Schedule B does not say that a row is a judgment rather than a line")
