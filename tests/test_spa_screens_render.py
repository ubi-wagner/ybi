"""A screen that cannot render is worse than a screen that is missing.

`PageHead is not defined` white-screened the classification queue — the one
screen the whole engagement is worked from — in the built application. React
does not fail a missing component at build time: Vite bundles it happily,
because `PageHead` is a legal identifier that might be defined at runtime, and
it throws the moment the component renders. The page goes blank and takes the
rest of the tree with it.

Nothing caught it. `tests/test_manual.py` checks that every screenshot the
manual references **exists**, and the file did exist — it was 6,490 bytes of
empty page against 78,000 for every other screen. The walk that produces it
waited a fixed interval and photographed whatever was there.

Two guards came out of that, and this is the cheap one: read every page
component, and fail on a UI primitive that is used but never imported.
`scripts/walk_manuals.py` carries the other — it now fails a screenshot with
nothing on it, which is the failure a file-exists test cannot see.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "web" / "src"
UI = WEB / "components" / "ui.jsx"

#: Things that look like a component in JSX and are not one of ours.
NATIVE = {"React", "Fragment"}


def exported_primitives() -> set[str]:
    return set(re.findall(r"export (?:function|const) ([A-Z]\w+)", UI.read_text()))


def components():
    for path in sorted(WEB.rglob("*.jsx")):
        if path == UI:
            continue
        yield path


def names_in_scope(src: str) -> set[str]:
    """Everything a component could legally reference: what it imports, and
    what it defines itself."""
    scope: set[str] = set()
    for block in re.finditer(r"import\s*\{([^}]*)\}\s*from", src):
        scope |= {n.strip().split(" as ")[-1]
                  for n in block.group(1).split(",") if n.strip()}
    # A default import, and a namespace one.
    scope |= set(re.findall(r"import\s+([A-Z]\w+)\s+from", src))
    scope |= set(re.findall(r"import\s+\*\s+as\s+([A-Z]\w+)", src))
    # Declared in the file.
    scope |= set(re.findall(r"(?:function|const|class)\s+([A-Z]\w+)", src))
    return scope | NATIVE


@pytest.mark.parametrize("path", list(components()),
                         ids=lambda p: p.name)
def test_every_primitive_a_screen_renders_is_in_scope(path):
    src = path.read_text()
    used = set(re.findall(r"<([A-Z]\w+)", src))
    missing = sorted((used & exported_primitives()) - names_in_scope(src))
    assert not missing, (
        f"{path.name} renders {', '.join(missing)} without importing it. "
        f"Vite bundles this without complaint and React throws when the "
        f"component renders, which white-screens the whole page — exactly "
        f"how the classification queue was broken."
    )


def test_the_screenshot_walk_refuses_a_blank_photograph():
    """The other half. A file-exists test passes on an empty file, and an
    empty screenshot in a manual teaches a reader that the screen is
    empty."""
    walk = (Path(__file__).resolve().parent.parent / "scripts"
            / "walk_manuals.py").read_text()
    assert "photographed blank" in walk
    assert "innerText" in walk, ("the walk has to read what is on the page, "
                                 "not just how long it waited")
