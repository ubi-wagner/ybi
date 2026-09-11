#!/usr/bin/env python3
"""Photograph each role's screens, so the manual cannot describe one that
does not exist.

    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/walk_manuals.py

Every shot here is a real screen, signed in as the person the manual is
written for, against the real ledger. A manual illustrated with a mock-up is
a manual that goes stale the first time somebody moves a button.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("web/public/help")
CHROME_CANDIDATES = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium/chrome-linux/chrome",
]

#: email, path, filename, what it shows, an optional tab to click first
SHOTS = [
    # Everyone
    ("hruby@ybi.org",   "/",           "m-home",          "Your landing page", None),
    ("hruby@ybi.org",   "/timesheet",  "m-timesheet",     "Building a timesheet", None),
    ("hruby@ybi.org",   "/certify",    "m-certify",       "Signing for your own effort", None),
    ("hruby@ybi.org",   "/documents",  "m-documents",     "Sending a document in", None),
    # Controller
    ("tom@ybi.org",     "/",           "m-home-controller", "The controller's landing", None),
    ("tom@ybi.org",     "/classify",   "m-classify",      "The classification queue", None),
    ("tom@ybi.org",     "/reconcile",  "m-reconcile",     "Schedule A-1", None),
    ("tom@ybi.org",     "/rates",      "m-rates",         "Sealing, and the rate", None),
    ("tom@ybi.org",     "/imports",    "m-imports",       "Importing from QuickBooks", None),
    # Portfolios
    ("hruby@ybi.org",   "/space",      "m-space",         "Buildings and the rent roll", None),
    ("hruby@ybi.org",   "/inventory",  "m-inventory",     "The equipment register", None),
    ("hruby@ybi.org",   "/evidence",   "m-evidence",      "Filing what people send in", None),
    # The shelf, as the person who arrives wanting to read something rather
    # than to file anything — which is the auditor, who holds no portfolio.
    ("auditor@ybi.org", "/library",    "m-library",       "The document library", None),
    ("auditor@ybi.org", "/reports",    "m-reports",       "Reports and invoices", None),
    ("sgaffney@ybi.org", "/contracts", "m-contracts",     "Contracts and what each earns", None),
    ("sgaffney@ybi.org", "/contracts/codes", "m-charge-codes", "Charge codes and who may charge them", None),
    ("sgaffney@ybi.org", "/chart",     "m-chart",         "The 2026 chart", None),
    # Administration
    ("bewing@ybi.org",  "/people",     "m-people",        "The roster", None),
    ("bewing@ybi.org",  "/people",     "m-people-gaps",   "Payroll without accounts",
     "Payroll without accounts"),
    ("bewing@ybi.org",  "/",           "m-home-admin",    "The administrator's landing", None),
    # Reading only
    ("auditor@ybi.org", "/",           "m-home-auditor",  "The auditor's landing", None),
]


def chrome() -> str:
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    raise SystemExit("no chromium found under /opt/pw-browsers")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    pw_pass = os.environ.get("YBI_SEED_PASSWORD", "")
    if not pw_pass:
        raise SystemExit("YBI_SEED_PASSWORD is required.")
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome())
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        signed_in = None
        for email, path, name, what, tab in SHOTS:
            if email != signed_in:
                page.context.clear_cookies()
                page.goto(args.base + "/", wait_until="networkidle")
                page.fill("input[type=email]", email)
                page.fill("input[type=password]", pw_pass)
                page.click("button[type=submit]")
                page.wait_for_timeout(1500)
                signed_in = email
            page.goto(args.base + path, wait_until="networkidle")
            page.wait_for_timeout(1400)
            if tab:
                try:
                    page.locator(f"button:has-text('{tab}')").first.click()
                    page.wait_for_timeout(900)
                except Exception:
                    pass
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            print(f"  {name:22} {what}", flush=True)
        browser.close()
    print(f"\n{len(SHOTS)} screens photographed into {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
