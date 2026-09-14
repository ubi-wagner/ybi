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

import json

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "web" / "src" / "components" / "Manual.jsx"
HELP = ROOT / "web" / "src" / "pages" / "Help.jsx"
NAV = ROOT / "web" / "src" / "App.jsx"
SHOTS = ROOT / "web" / "public" / "help"
MANIFEST = SHOTS / "taken.json"

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
    """Every screenshot either document shows.

    This read only Manual.jsx, so the 24 numbered files Help.jsx points at
    were covered by nothing at all — and `05a-reconcile.png` sat on the
    chapter telling the controller to reconcile first, showing "Cross-
    reference points 10" against eleven, no payroll register, and a nav
    carrying tabs that had been renamed.
    """
    return sorted(set(re.findall(r"shot:\s*\[\"([^\"]+)\"", source()))
                  | set(re.findall(r'src="/help/([^"]+)\.png"', HELP.read_text())))


def taken() -> dict:
    """What scripts/walk_manuals.py actually produced, as it recorded it."""
    assert MANIFEST.exists(), (
        "web/public/help/taken.json is missing. Run the walk: "
        "PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/walk_manuals.py")
    return json.loads(MANIFEST.read_text())


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


@pytest.mark.parametrize("shot", SHOT_IDS)
def test_every_screenshot_the_manual_shows_is_one_the_walk_takes(shot):
    """Existing is not the same as being retaken.

    A file-exists test passes for ever on a photograph nothing regenerates,
    which is how the Help page came to show a reconciliation screen with ten
    control points and a nav that had been rebuilt since. The walk writes
    down what it produced; a shot that is not in that list is one somebody
    took by hand and nobody will take again.

    This is the derive-don't-keep rule the review script already follows for
    the endpoints each screen calls.
    """
    assert shot in taken(), (
        f"{shot}.png is shown in the manual and scripts/walk_manuals.py does "
        f"not produce it, so nothing will ever retake it. Add it to SHOTS — "
        f"with steps, if it needs a tab or a panel opened — or stop showing "
        f"a picture that cannot be refreshed.")


def test_nothing_is_kept_that_nothing_shows():
    """The other direction: 23 files were on disk that no page referenced."""
    on_disk = {p.stem for p in SHOTS.glob("*.png")}
    assert not on_disk - set(SHOT_IDS), (
        "screenshots on disk that no page shows: "
        + ", ".join(sorted(on_disk - set(SHOT_IDS)))
        + ". They are shipped to every visitor and read by nobody.")


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


def test_the_nav_lets_a_controller_everywhere_the_api_does():
    """`CONTROLLER` reaches everything — CLAUDE.md says so and auth.py means
    it: every narrow gate is `require_portfolio(X, Portfolio.CONTROLLER)`.

    `tabsFor` did not. It tested `held.has(needs)` alone, so Tom — who holds
    the portfolio that reaches everything — was offered four screens fewer
    than he is entitled to and would have had to know the URLs for Evidence,
    Space, Inventory and Contracts.

    A nav stricter than the API is the same class of defect as one looser
    than it. Both mean the screen and the server disagree about who you are;
    one shows a tab that answers 403, the other hides work somebody is
    supposed to do.
    """
    auth = (ROOT / "app" / "auth.py").read_text()
    narrow = re.findall(r"require_\w+ = require_portfolio\((.*?)\)", auth)
    admits_controller = [n for n in narrow if "Portfolio.CONTROLLER" in n]
    assert len(admits_controller) >= 4, (
        "the narrow portfolio gates no longer admit CONTROLLER; if that is "
        "deliberate, this test and the nav both need to change with it")

    nav = NAV.read_text()
    block = nav[nav.index("function tabsFor"):nav.index("export default")]
    assert 'held.has("CONTROLLER")' in block, (
        "tabsFor no longer lets a controller into the narrow portfolio "
        "screens, but every one of those endpoints still admits them")

    manual = MANUAL.read_text()
    assert 'includes("CONTROLLER")' in manual, (
        "the manual gates chapters more strictly than the nav offers tabs, "
        "so a controller gets a screen with no chapter explaining it")


def test_the_manual_counts_the_controls_the_schema_defines():
    """"Ten cross-reference points" was in four places and wrong in all of them.

    The Help chapter's prose, its caption, its "four of the ten are worth
    knowing by name", and the in-application manual's caption. The eleventh
    control — the payroll register against the ledger's wage accounts — is
    the one CLAUDE.md calls the one that pays for itself: it is how a $45,000
    donor credit in an intern wage account was found, having moved the fringe
    rate from 22.45% to 21.90%, and none of the other ten touches the
    register. The chapter that tells the controller to reconcile before
    classifying anything did not mention it.

    A figure in a document for somebody else is read off the record, not
    recalled. The register is in the schema, so the count is read from there.
    """
    body = ""
    for path in sorted((ROOT / "app" / "sql").glob("*.sql"), reverse=True):
        src = path.read_text()
        i = src.find("CREATE OR REPLACE VIEW v_statement_reconciliation AS")
        if i == -1:
            i = src.find("CREATE VIEW v_statement_reconciliation AS")
        if i != -1:
            j = min((k for k in (src.find("\nCOMMENT ON", i + 10),
                                 src.find("\nCREATE ", i + 10)) if k != -1),
                    default=len(src))
            body = src[i:j]
            break
    assert body, "v_statement_reconciliation is not defined in any migration"

    # Each control is named in the evaluability CASE, which is the one place
    # every control has to appear: a control missing from it falls to the
    # ELSE and is treated as evaluable over no data, which is the defect 029
    # was written to fix.
    controls = {c for c in re.findall(r"WHEN\s+'([A-Z][A-Z_]{3,})'", body)
                if not c.startswith("WHEN")}
    n = len(controls)
    assert n >= 11, f"only found {n} controls in the register: {sorted(controls)}"

    words = {10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen"}
    said = words.get(n, str(n))
    for doc, src in (("Help.jsx", HELP.read_text()),
                     ("Manual.jsx", source())):
        for wrong in (w for k, w in words.items() if k != n):
            assert f"{wrong} cross-reference" not in src.lower(), (
                f"{doc} says {wrong!r} cross-reference points; the register "
                f"defines {n}. The count is in the schema — read it, do not "
                f"recall it.")
        if "cross-reference point" in src.lower():
            assert f"{said} cross-reference point" in src.lower(), (
                f"{doc} names a number of cross-reference points that is not "
                f"{said}")
    assert "PAYROLL_REGISTER" in controls, (
        "the payroll register is no longer one of the controls; the manual "
        "chapter describing it needs to change with it")
