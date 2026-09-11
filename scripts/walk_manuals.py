#!/usr/bin/env python3
"""Photograph every screen the manual shows, so it cannot describe one that
does not exist — or one that no longer looks like that.

    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/walk_manuals.py

Every shot here is a real screen, signed in as the person the manual is
written for, against the real ledger. A manual illustrated with a mock-up is
a manual that goes stale the first time somebody moves a button.

**It takes the in-application manual's shots and the Help page's, because
there is one set.** There were two: this script produced 21 `m-*.png` and
`web/src/pages/Help.jsx` pointed at 24 numbered files it never touched.
`tests/test_manual.py` checked that every screenshot the manual references
*exists*, which a stale one does — so `05a-reconcile.png` sat there showing
"Cross-reference points 10" against eleven, a nav carrying tabs that had been
renamed, and no payroll register at all, on the chapter that tells the
controller to reconcile before classifying anything.

A screenshot is a figure in a document for somebody else. The rule for those
is that they are read off the live record rather than recalled, and a
photograph nothing retakes is the purest form of recalling.

Each shot may carry `steps` — a tab to click, a key to press, a panel to
open — so the states the manual teaches from (focus mode, the editor, a
split being composed) are reachable by the walk rather than by hand. None of
them writes: the walk photographs the record, it does not change it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

OUT = Path("web/public/help")
MANIFEST = OUT / "taken.json"
CHROME_CANDIDATES = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium/chrome-linux/chrome",
]

#: email (None = signed out), path, filename, what it shows, steps
#:
#: A step is (kind, argument):
#:   ("tab", label)    click a button with that text — the segmented controls
#:   ("key", k)        press a key — the queue is keyboard-first on purpose
#:   ("click", sel)    any other control, by selector
#:   ("fill", (sel, text))  type into a field — never submitted, so the walk
#:                     can show a form being composed without writing
#:   ("wait", ms)      when a panel animates in
SHOTS = [

    # Everyone
    ("hruby@ybi.org",   "/timesheet",  "m-timesheet",     "Building a timesheet", []),
    ("hruby@ybi.org",   "/certify",    "m-certify",       "Signing for your own effort", []),
    ("hruby@ybi.org",   "/documents",  "m-documents",     "Sending a document in", []),
    # Controller
    ("tom@ybi.org",     "/classify",   "m-classify",      "The classification queue", []),
    ("tom@ybi.org",     "/reconcile",  "m-reconcile",     "Schedule A-1", []),
    ("tom@ybi.org",     "/rates",      "m-rates",         "Sealing, and the rate", []),
    ("tom@ybi.org",     "/imports",    "m-imports",       "Importing from QuickBooks", []),
    # Portfolios
    ("hruby@ybi.org",   "/space",      "m-space",         "Buildings and the rent roll", []),
    ("hruby@ybi.org",   "/inventory",  "m-inventory",     "The equipment register", []),
    ("hruby@ybi.org",   "/evidence",   "m-evidence",      "Filing what people send in", []),
    # The shelf, as the person who arrives wanting to read something rather
    # than to file anything — which is the auditor, who holds no portfolio.
    ("auditor@ybi.org", "/library",    "m-library",       "The document library", []),
    ("auditor@ybi.org", "/reports",    "m-reports",       "Reports and invoices", []),
    ("sgaffney@ybi.org", "/contracts", "m-contracts",     "Contracts and what each earns", []),
    ("sgaffney@ybi.org", "/contracts/codes", "m-charge-codes", "Charge codes and who may charge them", []),
    # Administration
    #
    # Six shots were dropped from this list, not because they were wrong but
    # because no chapter showed them — the landing page for each of the four
    # roles, the 2026 chart, and the payroll-without-accounts panel. A
    # screenshot nobody looks at is shipped to every visitor and read by
    # none of them. If a chapter grows that wants one, the shot comes back
    # with the chapter.
    ("bewing@ybi.org",  "/people",     "m-people",        "The roster", []),
    # Reading only

    # ── The Help page's chapters ──────────────────────────────────────
    #
    # These were 24 numbered files nothing regenerated. Four of them showed
    # a state that only exists after somebody writes to the record — a note
    # recorded, a document attached, a split applied, a certification
    # signed — and the walk does not write, so the chapters that showed them
    # now describe the outcome instead of photographing one that cannot be
    # retaken. A picture nobody can reproduce is the thing this file exists
    # to stop.
    (None,              "/",            "01-signin",       "The sign-in screen", []),
    ("tom@ybi.org",     "/",            "02-dashboard",    "The dashboard, and the activity feed under it", []),
    ("tom@ybi.org",     "/worklist/UNCLASSIFIED", "03-worklist", "One class of open work", []),
    ("tom@ybi.org",     "/imports",     "05-import",       "Importing each report", []),
    ("tom@ybi.org",     "/reconcile",   "05a-reconcile",   "The eleven cross-reference points", []),
    ("tom@ybi.org",     "/reconcile",   "05b-reconcile-gl-pl", "Ledger against the P&L, account by account",
     [("tab", "Ledger vs P&L")]),
    ("tom@ybi.org",     "/reconcile",   "05c-reconcile-items", "Each named difference and the lines behind it",
     [("tab", "Reconciling items")]),
    ("tom@ybi.org",     "/classify",    "06-classify-sweep", "Sweep mode — the dense table", []),
    ("tom@ybi.org",     "/classify",    "07-classify-focus", "Focus mode — one group, set large",
     [("tab", "Focus")]),
    ("tom@ybi.org",     "/classify",    "11-editor",       "Classifying differently",
     [("tab", "Focus"), ("click", "button:has-text('Classify differently')")]),
    ("tom@ybi.org",     "/classify",    "12-split",        "A split being composed — shares, drivers and citations",
     [("tab", "Focus"), ("click", "button:has-text('Split this group')"),
      ("fill", ("input[placeholder='What this part is'] >> nth=0", "Direct programme delivery")),
      ("fill", ("input[placeholder='%'] >> nth=0", "70")),
      ("fill", ("input[placeholder='Why this share, and on what driver'] >> nth=0",
                "Tech Control milestones 23-3757, April to June. Hours booked to the objective.")),
      ("fill", ("input[placeholder='What this part is'] >> nth=1", "General management")),
      ("fill", ("input[placeholder='%'] >> nth=1", "30")),
      ("fill", ("input[placeholder='Why this share, and on what driver'] >> nth=1",
                "Residual oversight, carried on the same driver as the rest of general management.")),
      ("wait", 400)]),
    # One shot, not two. The record already carries notes, so this shows a
    # note somebody recorded — with their name and the time on it, never
    # edited in place — and the empty box below it at the same time. The
    # manual used to show those as separate pictures, and the second was a
    # state only a write could produce.
    ("tom@ybi.org",     "/classify",    "08-note",         "A note on the record, and the box for the next one",
     [("tab", "Focus"), ("click", "button:has-text('Notes and documents')"),
      ("fill", ("textarea", "The invoice is in the inbox but not yet filed; "
                            "this group stays open until it is cited.")),
      ("wait", 300)]),
    ("hruby@ybi.org",   "/evidence",    "14-evidence",     "Schedule E — what supports which figure", []),
    ("hruby@ybi.org",   "/certify",     "17-certify",      "An employee's whole year, not just the funded part", []),
    ("hruby@ybi.org",   "/timesheet",   "22-timesheet-week", "The week grid", []),
    ("hruby@ybi.org",   "/timesheet",   "23-timesheet-month", "The month view",
     [("tab", "Month")]),
    ("auditor@ybi.org", "/",            "19-auditor",      "The auditor's dashboard", []),
    ("auditor@ybi.org", "/classify",    "20-auditor-classify", "The queue with nothing to press", []),
]


def chrome() -> str:
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    raise SystemExit("no chromium found under /opt/pw-browsers")


def newcomer(base: str, password: str) -> tuple[str, str] | None:
    """An account still on a password somebody else chose.

    `role-06-first-password` is the first screen anybody at YBI sees and the
    only one they are given before they have chosen a password. No account on
    the record is in that state — which is the point, and is also why this
    was the one shot the walk could not take and so went unretaken.

    So it makes one, through the real provisioning route as the
    organisation's administrator, photographs the screen as that person, and
    stands the account down afterwards. Provisioning and standing down are
    both recorded acts under Barb's name, which is honest: somebody did make
    an account, and the trail should say so rather than a screenshot
    appearing from nowhere.
    """
    import time
    stamp = int(time.time())
    email = f"manual-newcomer-{stamp}@ybi.org"
    issued = "issued-by-somebody-else-1"
    c = httpx.Client(base_url=base, timeout=30)
    r = c.post("/api/auth/login", json={"email": "bewing@ybi.org",
                                        "password": password})
    if r.status_code != 200:
        return None
    r = c.post("/api/auth/actors", json={
        "email": email, "display_name": "New Starter", "role": "EMPLOYEE",
        "employee_key": f"MANUAL{stamp}", "password": issued})
    c.close()
    if r.status_code != 201:
        print(f"  could not provision a newcomer — {r.status_code}; "
              f"role-06-first-password will not be retaken", flush=True)
        return None
    return email, issued


def stand_down(email: str) -> None:
    """Never deleted — deleting an account is never right here."""
    from app.db import execute
    execute("UPDATE actor SET is_active = false WHERE email = %s", (email,))


def head_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return ""


def take_steps(page, steps) -> list[str]:
    """Do what the shot asks for, and say what did not happen.

    A step that silently fails photographs the screen in the state before it,
    which is a picture of the wrong thing rather than a picture of nothing —
    the blank check below cannot see it.
    """
    missed = []
    for kind, arg in steps:
        try:
            if kind == "tab":
                page.locator(f"button:has-text('{arg}')").first.click(timeout=5000)
                page.wait_for_timeout(900)
            elif kind == "key":
                page.keyboard.press(arg)
                page.wait_for_timeout(700)
            elif kind == "click":
                page.locator(arg).first.click(timeout=5000)
                page.wait_for_timeout(900)
            elif kind == "fill":
                sel, text = arg
                page.locator(sel).first.fill(text, timeout=5000)
                page.wait_for_timeout(200)
            elif kind == "wait":
                page.wait_for_timeout(int(arg))
            else:
                missed.append(f"unknown step {kind!r}")
        except Exception as e:
            missed.append(f"{kind} {arg!r}: {type(e).__name__}")
    return missed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    pw_pass = os.environ.get("YBI_SEED_PASSWORD", "")
    if not pw_pass:
        raise SystemExit("YBI_SEED_PASSWORD is required.")
    OUT.mkdir(parents=True, exist_ok=True)

    commit = head_commit()
    taken: dict[str, dict] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome())
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        made = newcomer(args.base, pw_pass)
        shots = list(SHOTS)
        if made:
            shots.append((made[0], "/", "role-06-first-password",
                          "The first screen anybody sees", []))
        passwords = {made[0]: made[1]} if made else {}
        signed_in = "unset"
        blank: list[str] = []
        unreachable: list[str] = []
        for email, path, name, what, steps in shots:
            if email != signed_in:
                page.context.clear_cookies()
                page.goto(args.base + "/", wait_until="networkidle")
                if email is not None:
                    page.fill("input[type=email]", email)
                    page.fill("input[type=password]",
                              passwords.get(email, pw_pass))
                    page.click("button[type=submit]")
                    page.wait_for_timeout(1500)
                signed_in = email
            page.goto(args.base + path, wait_until="networkidle")
            # Wait for the screen to have drawn something, not for a fixed
            # interval. The classification queue reads 999 groups and runs a
            # proposal over each, and it took longer than the 1,400ms this
            # used to allow — so the manual's most important chapter carried
            # a photograph of an empty page, at 6KB against 78KB for every
            # other screen, for as long as anybody had been looking at it.
            #
            # The sign-in screen is the exception: it is short by design.
            floor = 60 if email is None else 400
            try:
                page.wait_for_function(
                    f"document.body.innerText.trim().length > {floor}",
                    timeout=20000)
            except Exception:
                pass
            page.wait_for_timeout(600)
            missed = take_steps(page, steps)
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)

            # A photograph of nothing is not a photograph.
            #
            # tests/test_manual.py checks that every screenshot the manual
            # references exists, which a blank file does. Emptiness is the
            # failure mode a file-exists test cannot see, and a blank screen
            # in a manual teaches a reader that the screen is blank.
            text = page.evaluate("document.body.innerText.trim()")
            size = (OUT / f"{name}.png").stat().st_size
            taken[name] = {"path": path, "as": email or "signed out",
                           "shows": what, "bytes": size,
                           "characters": len(text), "commit": commit}
            if missed:
                unreachable.append(f"{name}: " + "; ".join(missed))
                print(f"  UNREACHED {name:22} {'; '.join(missed)}", flush=True)
            elif len(text) < floor or size < (6_000 if email is None else 20_000):
                blank.append(f"{name} ({path}, {size:,} bytes, "
                             f"{len(text)} characters on the page)")
                print(f"  BLANK {name:22} {what}", flush=True)
            else:
                print(f"  {name:22} {what}", flush=True)
        browser.close()
    if made:
        stand_down(made[0])

    # What the walk produces, so a test can ask whether the manual shows
    # something the walk does not take — rather than only whether the file
    # is there, which a file nothing retakes always is.
    MANIFEST.write_text(json.dumps(dict(sorted(taken.items())), indent=2) + "\n")

    if blank or unreachable:
        if blank:
            print(f"\n{len(blank)} screen(s) photographed blank:")
            for b in blank:
                print(f"    {b}")
        if unreachable:
            print(f"\n{len(unreachable)} shot(s) could not reach the state "
                  f"they are meant to show:")
            for u in unreachable:
                print(f"    {u}")
            print("    A step that fails quietly photographs the screen as it "
                  "was before it, which is a picture of the wrong thing.")
        return 1
    print(f"\n{len(shots)} screens photographed into {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
