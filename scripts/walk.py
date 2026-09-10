#!/usr/bin/env python3
"""The capability walk.

Drives the deployed application the way the people who use it will, in the
order they will, and photographs each step. The screenshots become the
manual, so the manual cannot describe a screen that does not exist.

    PYTHONPATH=. .venv/bin/python scripts/walk.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
SHOTS = Path("web/public/help")
PW = "SandboxDrive2026!"
STEPS: list[str] = []


def shot(page, name: str, note: str = "") -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(450)
    page.screenshot(path=str(SHOTS / f"{name}.png"))
    STEPS.append(f"  {name:26} {note}")
    print(f"  {name:26} {note}", flush=True)


def sign_in(page, email: str) -> None:
    page.goto(BASE + "/", wait_until="networkidle")
    page.fill("input[type=email]", email)
    page.fill("input[type=password]", PW)
    page.click("button[type=submit]")
    page.wait_for_timeout(1200)


def sign_out(page) -> None:
    page.click("text=Sign out")
    page.wait_for_timeout(900)


def main() -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
            args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1360, "height": 960},
                                  device_scale_factor=1,
                                  accept_downloads=True)
        page = ctx.new_page()

        # ── 1. Sign in as the controller ────────────────────────────
        page.goto(BASE + "/", wait_until="networkidle")
        page.fill("input[type=email]", "tom@ybi.org")
        page.fill("input[type=password]", PW)
        shot(page, "01-signin", "sign-in, credentials entered")
        page.click("button[type=submit]")
        page.wait_for_timeout(1800)
        shot(page, "02-dashboard", "controller dashboard")

        # the work list and activity feed further down the dashboard
        page.mouse.wheel(0, 1100)
        shot(page, "03-worklist", "what is left, on the dashboard")
        page.mouse.wheel(0, 1400)
        shot(page, "04-activity", "the activity feed")
        page.mouse.wheel(0, -3000)

        # ── 2. Import ───────────────────────────────────────────────
        page.goto(BASE + "/imports", wait_until="networkidle")
        shot(page, "05-import", "schedule A — what was loaded and whether it ties")

        # ── 3. Classify, sweep ──────────────────────────────────────
        page.goto(BASE + "/classify", wait_until="networkidle")
        page.wait_for_timeout(1400)
        shot(page, "06-classify-sweep", "the queue in sweep mode")

        # ── 4. Classify, focus ──────────────────────────────────────
        page.keyboard.press("f")
        page.wait_for_timeout(900)
        shot(page, "07-classify-focus", "one group, at size")

        # notes and documents on the group
        page.click("text=Notes and documents")
        page.wait_for_timeout(700)
        note = page.locator("textarea.note-input")
        note.fill(
            "JumpStart is the pass-through for the ODSA Entrepreneurial "
            "Services Program. This is state funding, not federal, so it is "
            "outside the SEFA — recorded here so the next person does not "
            "have to work it out again.")
        shot(page, "08-note", "a note being written against the group")
        page.click("button:has-text('Add note')")
        page.wait_for_timeout(1100)
        shot(page, "09-note-recorded", "the note, recorded with author and time")

        # attach a document to the group
        page.set_input_files(
            "input[type=file]",
            "docs/source-documents/accounting-records/"
            "2025_Profit-and-Loss_QuickBooks.xlsx")
        page.wait_for_timeout(1800)
        shot(page, "10-attached", "one upload, fanned out to every line in the group")

        # classify it, through the editor
        page.click("button:has-text('Classify differently')")
        page.wait_for_timeout(800)
        shot(page, "11-editor", "classifying differently — pool, grade, reasoning")
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)

        # ── 5. Splitting a mixed group ──────────────────────────────
        # Portfolio consulting is the largest open judgment in the ledger and
        # is not one thing, so it is the honest example.
        page.fill("input[placeholder='Account or vendor   /']", "S-Gen")
        page.wait_for_timeout(1400)
        page.click("button:has-text('Split this group')")
        page.wait_for_timeout(600)
        rows = [("Direct programme consulting", "60",
                 "Portfolio company engagements delivered under ESP; driver is "
                 "the consultant statements of work by company.",
                 "2 CFR 200.413(a)"),
                ("General incubator support", "40",
                 "Advisory time benefiting the portfolio as a whole, allocable "
                 "to G&A rather than to any one objective.",
                 "2 CFR 200.414(a)")]
        for i, (label, share, why, cite) in enumerate(rows):
            part = page.locator(".split-part").nth(i)
            part.locator("input").nth(0).fill(label)
            part.locator("input").nth(1).fill(share)
            part.locator("input").nth(2).fill(why)
            part.locator("input").nth(3).fill(cite)
        shot(page, "12-split", "a mixed group being split into parts")
        page.click("button:has-text('Record the split')")
        page.wait_for_timeout(2000)
        shot(page, "13-split-recorded", "the split, reconciled line by line")
        page.fill("input[placeholder='Account or vendor   /']", "")
        page.wait_for_timeout(900)

        # ── 5. Evidence register ────────────────────────────────────
        page.goto(BASE + "/evidence", wait_until="networkidle")
        page.wait_for_timeout(1000)
        shot(page, "14-evidence", "schedule E — the document register")

        # ── 6. Lanes and rates ──────────────────────────────────────
        page.goto(BASE + "/lanes", wait_until="networkidle")
        page.wait_for_timeout(900)
        shot(page, "15-lanes", "schedule C — scenario lanes")
        page.goto(BASE + "/rates", wait_until="networkidle")
        page.wait_for_timeout(900)
        shot(page, "16-rates", "schedule D — sealed before any rate exists")

        # ── 7. The auditor's copy ───────────────────────────────────
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(1200)
        with page.expect_download() as dl:
            page.click("text=Download audit package")
        path = dl.value.path()
        size = Path(path).stat().st_size if path else 0
        STEPS.append(f"  download                   audit package, {size:,} bytes")
        print(f"  download                   audit package, {size:,} bytes", flush=True)
        page.wait_for_timeout(900)

        # ── 8. The employee ─────────────────────────────────────────
        sign_out(page)
        sign_in(page, "bewing@ybi.org")
        shot(page, "17-certify", "the employee sees her own distribution and nothing else")
        page.check("input[type=checkbox]")
        page.wait_for_timeout(300)
        page.click("button:has-text('Sign certification')")
        page.wait_for_timeout(1600)
        shot(page, "18-certified", "signed — name, time and the numbers signed for")

        # ── 9. The auditor ──────────────────────────────────────────
        sign_out(page)
        sign_in(page, "auditor@ybi.org")
        shot(page, "19-auditor", "the auditor's dashboard — read only, by design")
        page.goto(BASE + "/classify", wait_until="networkidle")
        page.wait_for_timeout(1400)
        shot(page, "20-auditor-classify", "the auditor can read the queue, not change it")

        # ── 10. The manual itself ───────────────────────────────────
        page.goto(BASE + "/help", wait_until="networkidle")
        page.wait_for_timeout(900)
        shot(page, "21-help", "the manual, served by the application")

        browser.close()

    print(f"\n{len(STEPS)} steps captured into {SHOTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
