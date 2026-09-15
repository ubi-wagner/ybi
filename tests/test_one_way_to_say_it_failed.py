"""A refusal reaches a person as a sentence, from one place.

`api.js::explain()` turns what the server threw into what a person reads: it
strips the status code `req()` puts on the front, unwraps `{"detail": …}`, and
pulls the sentence out of a structured refusal. Its own comment says why a
screen must not do that itself — *a screen that unpicked them itself would be
a second copy of this function, free to disagree with the first about what the
server said.*

Forty screens did it themselves. `String(e.message || e)` printed **"409:
programme space names the cost objective it serves"** into a toast, so every
refusal in the system reached its reader with the plumbing on the front; and
ten of them then hand-rolled the strip and the unwrap `explain` already does,
one of those through a `JSON.parse` of a string `explain` had already parsed.

It is `money()` in the error path: eight spellings of one formatter, and the
fix is the same — one definition, and a test that fails a ninth.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "src"
API = SRC / "api.js"


def screens() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.jsx"))


def test_explain_is_defined_once():
    body = API.read_text()
    assert "export function explain(" in body, "explain() is gone from api.js"
    assert len(re.findall(r"function explain\(", body)) == 1, (
        "explain() is defined more than once in api.js")


def test_no_screen_reads_a_message_off_an_error_itself():
    """`String(e.message || e)` is the raw throw, status code and all."""
    offenders = []
    for f in screens():
        for n, line in enumerate(f.read_text().split("\n"), 1):
            if re.search(r"String\((\w+)\.message \|\| \1\)", line):
                offenders.append(f"{f.relative_to(ROOT)}:{n}")
            if re.search(r"\b(?:err?|error)\?\.message\b", line):
                offenders.append(f"{f.relative_to(ROOT)}:{n}")
    assert not offenders, (
        "these print what was thrown rather than what it means — explain() is "
        "the one place that turns one into the other:\n  "
        + "\n  ".join(offenders))


def test_no_screen_re_strips_what_explain_already_stripped():
    """A second strip after `explain()` is a no-op that reads as load-bearing,
    and the next person keeps it because it looks like it is doing something.
    One of them was a `JSON.parse` of a string `explain` had already parsed."""
    offenders = []
    for f in screens():
        body = f.read_text()
        for pat, what in ((r"explain\([^)]*\)\s*\n?\s*\.replace\(/\^\\d", "a second status strip"),
                          (r'explain\([^)]*\)[^\n]*\n[^\n]*JSON\.parse\(msg\)', "a second unwrap")):
            if re.search(pat, body):
                offenders.append(f"{f.relative_to(ROOT)}: {what}")
    assert not offenders, "\n  ".join(offenders)


def test_every_screen_imports_what_it_uses():
    """The check that found the one file in thirty-one.

    A bulk edit across the SPA reported success and left `explain()` called in
    a file that does not import it — a ReferenceError the build does not see,
    because an undefined identifier is only a fault when the line runs, and
    the line that runs is in a `catch`. Twenty-six of twenty-seven were right
    the last time this happened too, which is exactly the ratio that survives
    a reading of the diff.
    """
    missing = []
    for f in screens():
        body = f.read_text()
        if re.search(r"\bexplain\(", body) and not re.search(
                r"import \{[^}]*\bexplain\b[^}]*\} from", body):
            missing.append(str(f.relative_to(ROOT)))
    assert not missing, (
        "these call explain() without importing it, which is a "
        "ReferenceError in a catch block:\n  " + "\n  ".join(missing))


# ------------------------------------------- and the same check for Python --

def test_no_python_module_uses_a_name_it_does_not_have():
    """A `NameError` in a `catch` is invisible to everything but the failure.

    Three times in one sitting: a bulk edit left `explain()` called in a file
    that does not import it; `Decimal` was used in a new facilities helper
    with no import; and `AllocationBase` had been an unresolvable annotation
    on `_build_model` since it was written — the one undefined name in the
    application, sitting there because nobody had ever run the check.

    Python's is `pyflakes`, restricted to **undefined names**. The other
    things it reports — an unused local, an f-string with no placeholder —
    are style, and a sweep that mixes style into a correctness gate is one
    people learn to ignore, which is how the real entry gets dismissed.
    """
    import subprocess
    import sys

    try:
        import pyflakes  # noqa: F401
    except ImportError:                                   # pragma: no cover
        import pytest
        pytest.skip("pyflakes is not installed")

    out = subprocess.run([sys.executable, "-m", "pyflakes",
                          str(ROOT / "app"), str(ROOT / "scripts"),
                          str(ROOT / "tests")],
                         capture_output=True, text=True).stdout
    undefined = [ln for ln in out.splitlines() if "undefined name" in ln]
    assert not undefined, (
        "these use a name the module does not have, which is a NameError on "
        "the line that runs:\n  " + "\n  ".join(undefined))
