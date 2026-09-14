"""Money reaches the screen to the cent, and through one formatter.

Eight screens carried their own spelling of `money()` and six of them rounded
to the whole dollar, so the payroll register printed as $1,835,047 on the home
screen and as $1,835,047.17 on the seal screen — one figure, two readings, at
the same moment. That is the defect this repository already records as 13.0%
and 2.2%, in the place a reviewer is most likely to tie a number.

Nothing behind the rendering was ever lossy: money is `Decimal` all the way
through the engine and `numeric` in the schema. Only the printing was, which
is why no control could see it.

Two rules, and the second is what keeps the first from decaying:

  * money prints to the cent, from `api.js`, and a blank prints as a blank;
  * no screen defines its own.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "src"
API = SRC / "api.js"


def test_money_prints_to_the_cent():
    """A cent is the unit a reviewer ties in."""
    src = API.read_text()
    body = src[src.index("export const money ="):]
    body = body[:body.index("\n};") + 3]

    assert "minimumFractionDigits: 2" in body and "maximumFractionDigits: 2" in body, (
        "api.js::money() no longer prints to the cent. The record holds "
        "1,835,047.17; rounding it in the rendering is how the same figure "
        "came to read two ways on two screens.")


def test_a_blank_is_not_printed_as_nil():
    """`Number(null || 0)` is 0, which is the intake rule broken on the way out.

    *There is no amount on this document* and *nobody has read it off yet*
    are different facts everywhere else in this system; they must not be the
    same pixel.
    """
    src = API.read_text()
    body = src[src.index("export const money ="):]
    body = body[:body.index("\n};") + 3]

    assert "Number(n || 0)" not in body, (
        "money() coerces a missing amount to zero, so 'nobody has read this "
        "off' prints identically to 'this is nil'.")
    assert "n === null" in body and "n === undefined" in body, (
        "money() no longer distinguishes a missing amount from a nil one")


def test_no_screen_defines_its_own_money():
    """One definition, or there are eight and six of them are wrong.

    The exception is a wrapper that *layers judgment* on the shared one —
    Awards decides that a ceiling of zero is a ceiling nobody has read — and
    those call money() rather than re-implement it. What fails here is a
    second formatter.
    """
    offenders = []
    for f in sorted(SRC.rglob("*.jsx")):
        src = f.read_text()
        for m in re.finditer(r"^\s*(?:const|function)\s+(\w*[Mm]oney\w*|dollars|usd|amt)\b",
                             src, re.M):
            # A wrapper is fine; a formatter is not.
            tail = src[m.start():m.start() + 400]
            if "toLocaleString" in tail.split("\n};")[0].split(";\n\n")[0]:
                offenders.append(f"{f.relative_to(ROOT)}: {m.group(1)}")
    assert not offenders, (
        "a screen formats money itself instead of importing money() from "
        "api.js — six of these rounded to the whole dollar: "
        + "; ".join(offenders))


def test_every_screen_that_shows_money_imports_it():
    """A screen calling money() without importing it is a blank page."""
    missing = []
    for f in sorted(SRC.rglob("*.jsx")):
        src = f.read_text()
        if not re.search(r"\bmoney\(", src):
            continue
        imp = re.search(r'^import \{([^}]*)\} from "\.\./api\.js";$', src, re.M)
        if not imp or "money" not in [x.strip() for x in imp.group(1).split(",")]:
            missing.append(str(f.relative_to(ROOT)))
    assert not missing, (
        "these screens call money() and do not import it: " + "; ".join(missing))
