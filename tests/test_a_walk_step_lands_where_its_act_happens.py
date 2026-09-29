"""A destination that cannot perform its step has to say where to go.

`test_the_nav_marks_are_the_walk_s_step_numbers` asks whether every walk
destination lands on a tab, and it passed for the whole life of this defect:
steps 7, 8 and 9 all go to `/review/rate`, which *is* a tab, and which is the
read-only workpaper. Sealing, unsealing and computing live on `/rates`, which
the eight-tab fold tagged as belonging to the other door — so the screen the
walk sends a controller to in order to seal could not seal, and said nothing
about where to.

Tom found it by finishing the classification queue and going to Rate. That is
the fifth time in this repository somebody using the system found a door no
sweep did, and it is the same reason every time: a sweep asks whether a route
answers, and a person asks whether they can get their job done.

**Reachable is not capable**, so this asks the second question — and asks it
in the weaker of the two honest forms. It does not require the destination to
perform the act, because a read-only workpaper carrying its own signature
door is a deliberate arrangement and a test that argued with it would be a
test arguing with correct code. It requires that the screen either **does the
act or links to the screen that does**. A dead end fails; a signpost passes.

The map of which call constitutes which act is hand-written and is meant to
be: what "sealing" is, is a fact about the domain, the way the six fringe
accounts in `v_payroll_reconciliation` are, and deriving it would be guessing
at the thing being asserted. Neither side of the comparison is hand-written —
the destinations come from `v_audit_walk`, the routes and components from
`App.jsx` — so a step that moves or a screen that loses its link fails here.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "src"
APP = WEB / "App.jsx"

#: The walk's steps that are *acts* rather than readings, and the request
#: helper each one is performed by.
ACTS = {
    "SEAL": "api.seal(",
    "RATE": "api.computeRate(",
    "CERTIFY": "api.certify(",
}


def routes() -> dict[str, str]:
    """Every SPA path and the component that renders it, from `App.jsx`."""
    return {m[1]: m[2] for m in re.finditer(
        r'<Route\s+path="([^"]+)"\s+element=\{<(\w+)', APP.read_text())}


def _file_for(component: str, source: str, base: Path) -> Path | None:
    m = re.search(rf'import\s+{component}\s+from\s+"([^"]+)"', source)
    if not m:
        return None
    p = (base / m.group(1)).resolve()
    return p if p.exists() else None


def reachable_source(component: str) -> str:
    """The component's source and that of everything it renders from our tree.

    A screen may host an act through a child — the rate workpaper does
    exactly that with the certification door — so reading only the page file
    would report a door that is plainly there.
    """
    path = _file_for(component, APP.read_text(), APP.parent)
    if not path:
        return ""
    # Transitively, because the depth is not a fact anybody should have to
    # know: `/review/rate` is `Review` → `RateReview` → `Certification`, and
    # a one-hop walk reported the signature door as missing from the screen
    # it is plainly on.
    seen, queue, out = {path}, [path], []
    while queue:
        cur = queue.pop()
        text = cur.read_text()
        out.append(text)
        for child in re.finditer(r'import\s+(\w+)\s+from\s+"(\.[^"]+)"', text):
            kid = _file_for(child.group(1), text, cur.parent)
            if kid and kid not in seen and kid.is_relative_to(WEB):
                seen.add(kid)
                queue.append(kid)
    return "\n".join(out)


def performer(call: str) -> str | None:
    """The one path whose screen makes this call."""
    for path, component in routes().items():
        if call in reachable_source(component):
            return path
    return None


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_every_act_of_the_walk_is_done_where_it_sends_you_or_says_where():
    from app.db import query

    steps = query("""SELECT key, seq, goes_to FROM v_audit_walk
                      WHERE period = %s ORDER BY seq""", ("2025",))
    if not steps:
        pytest.skip("no period loaded")

    table = routes()
    for s in steps:
        call = ACTS.get(s["key"])
        if not call:
            continue
        dest = s["goes_to"]
        component = table.get(dest)
        if component is None:              # `/review/rate` is `/review/:pane`
            for path, comp in sorted(table.items(), key=lambda kv: -len(kv[0])):
                stem = path.split("/:")[0]
                if ":" in path and dest.startswith(stem.rstrip("/") + "/"):
                    component = comp
                    break
        assert component, (
            f"walk step {s['seq']} ({s['key']}) goes to {dest}, which no "
            f"route in App.jsx renders")

        src = reachable_source(component)
        if call in src:
            continue                        # the act happens right there
        where = performer(call)
        assert where, (
            f"nothing in the SPA calls {call}, so walk step {s['seq']} "
            f"({s['key']}) cannot be done anywhere at all")
        assert f'to="{where}"' in src, (
            f"walk step {s['seq']} ({s['key']}) sends somebody to {dest}, "
            f"which does not call {call} and does not link to {where}, where "
            f"it happens. That is a map pointing at a wall — which is how a "
            f"controller who had finished the queue was handed a read-only "
            f"workpaper and told to seal on it.")


def test_the_rate_screen_says_why_there_is_no_rate():
    """"Not yet, because", never an empty list.

    The gate rendered its reasons from the open controls and the coverage,
    and with the queue finished and the books tying it printed a red heading
    with **nothing under it**. The reason that actually applied — the set is
    not sealed — was the one reason it had no branch for, so the screen told
    somebody who had done everything asked of them precisely nothing.
    """
    src = (WEB / "pages" / "RateReview.jsx").read_text()
    body = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)   # assert over code
    assert "sealed" in body.split("= d;")[0].split("const {")[-1], (
        "RateReview does not read `sealed` off the endpoint, so it cannot "
        "name the one reason a finished queue still has no rate.")
    assert "!sealed &&" in body, (
        "nothing in RateReview branches on an unsealed set, so the gate can "
        "still render a red heading over an empty list.")
