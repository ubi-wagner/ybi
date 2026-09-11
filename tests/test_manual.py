"""The manual has to describe screens that exist, to people who have them.

Two ways a manual rots. It illustrates a screen with a picture that is no
longer there — a broken image on the first page a new person sees. Or it
describes a job to somebody who cannot do it, which is worse, because they
will go looking for a tab that was never theirs and conclude the system is
broken.

Both are checkable without a browser, so they are checked here rather than
noticed by a user.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "web" / "src" / "components" / "Manual.jsx"
NAV = ROOT / "web" / "src" / "App.jsx"
SHOTS = ROOT / "web" / "public" / "help"

#: The portfolios themselves.
PORTFOLIOS = {"CONTROLLER", "INVENTORY", "PROJECT", "FACILITIES", "OFFICE"}


def sentinels(src: str) -> set[str]:
    """The non-portfolio words a gate function understands, read from it.

    This was a hardcoded {"staff", "admin"} and went stale the moment the
    review screens added "reader": a chapter gated on it was rejected as
    meaningless by a test that was simply out of date, which is the worst
    kind of failing test — it argues against a correct change. Reading the
    set out of the source means adding a sentinel to the nav cannot leave
    this behind again.
    """
    return set(re.findall(r'needs === "(\w+)"', src))


def source() -> str:
    return MANUAL.read_text()


def chapters() -> list[tuple[str, str, str]]:
    """(id, needs, title) for each chapter, read out of the source."""
    out = []
    for block in re.finditer(
            r"\{\s*id:\s*\"([^\"]+)\",\s*needs:\s*(null|\"[A-Za-z]+\"),\s*"
            r"title:\s*\"([^\"]+)\"", source()):
        out.append((block.group(1), block.group(2).strip('"'), block.group(3)))
    return out


def shot_ids() -> list[str]:
    return re.findall(r"shot:\s*\[\"([^\"]+)\"", source())


CHAPTERS = chapters()
SHOT_IDS = shot_ids()


def test_the_manual_has_chapters():
    assert len(CHAPTERS) >= 10, f"only parsed {len(CHAPTERS)} chapters"


@pytest.mark.parametrize("shot", SHOT_IDS)
def test_every_screenshot_the_manual_shows_exists(shot):
    """Run scripts/walk_manuals.py to take the ones that are missing."""
    path = SHOTS / f"{shot}.png"
    assert path.exists(), (
        f"the manual shows {shot}.png and there is no such file. Take it "
        f"with: PYTHONPATH=. python3 scripts/walk_manuals.py")
    assert path.stat().st_size > 2000, f"{shot}.png is suspiciously small"


@pytest.mark.parametrize("chapter_id,needs,title", CHAPTERS,
                         ids=[c[0] for c in CHAPTERS])
def test_every_chapter_is_gated_on_something_real(chapter_id, needs, title):
    assert needs in PORTFOLIOS | sentinels(NAV.read_text()) | {"null"}, (
        f"chapter {chapter_id!r} is gated on {needs!r}, which is neither a "
        f"portfolio nor a sentinel tabsFor() understands — so it will either "
        f"never show or show to the wrong people.")


@pytest.mark.parametrize("chapter_id,needs,title", CHAPTERS,
                         ids=[c[0] for c in CHAPTERS])
def test_a_chapter_about_a_portfolio_screen_names_that_portfolio(
        chapter_id, needs, title):
    """A chapter describing a screen somebody cannot open is worse than no
    chapter: it sends them looking for a tab that was never theirs."""
    nav = NAV.read_text()
    if needs in PORTFOLIOS:
        assert f'"{needs}"' in nav, (
            f"chapter {chapter_id!r} is gated on the {needs} portfolio, which "
            f"no tab in App.jsx requires — the reader would have no screen to "
            f"go to.")


def test_the_manual_is_gated_the_same_way_the_nav_is():
    """Both read employee_key, is_admin, portfolios and the auditor case. If
    they drift apart, somebody sees a chapter for a tab they do not have."""
    src = source()
    for token in ("employee_key", "is_admin", "portfolios", "AUDITOR"):
        assert token in src, (
            f"Manual.jsx no longer looks at {token}; it can no longer agree "
            f"with tabsFor() in App.jsx about who sees what.")


def test_the_manual_and_the_nav_understand_the_same_words():
    """`tabsFor` decides whether somebody gets a tab; `visible` decides
    whether they get the chapter explaining it. A word one knows and the
    other does not produces a screen with no instructions, or instructions
    for a screen that is not there.

    This is not hypothetical. "reader" was added to the nav when the review
    screens shipped and not to the manual, so the organisation's
    administrator would have been handed the Library tab and no chapter — the
    mismatch `visible` exists to prevent, running backwards.
    """
    nav = sentinels(NAV.read_text())
    manual = sentinels(MANUAL.read_text())
    assert nav == manual, (
        f"App.jsx and Manual.jsx disagree about how a screen is gated: "
        f"only the nav knows {sorted(nav - manual)}, only the manual knows "
        f"{sorted(manual - nav)}.")


def test_no_two_tabs_carry_the_same_name():
    """Three screens sit on Schedule E — where you send a document in, where
    the whole shelf is read, and where somebody says what a document proves.
    They are genuinely different jobs and the labels have to say so.

    They did not. The first was called "Documents", which is the generic word
    for all three, matched neither its own heading ("My documents") nor its
    job, and left an auditor looking at Documents / Library / Evidence with no
    way to tell which was which. A label that contains another label whole is
    the same failure one step removed.
    """
    nav = NAV.read_text()
    labels = [m[1] for m in re.findall(
        r'\["(/[^"]*)",\s*"([^"]+)",\s*"([^"]+)",', nav)]
    assert len(labels) == len(set(labels)), (
        f"two tabs share a label: "
        f"{sorted({l for l in labels if labels.count(l) > 1})}")
    for a in labels:
        for b in labels:
            if a is not b and a != b:
                assert a.lower() != b.lower(), f"{a!r} and {b!r} differ only in case"
