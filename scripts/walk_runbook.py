#!/usr/bin/env python3
"""Walk the Monday runbook through the real screens, and photograph it.

    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/walk_runbook.py \
        --base http://127.0.0.1:8140

**A runbook nobody has walked is a list of things somebody believes.** This
one drives every step of `docs/MONDAY_RUNBOOK.md` in a browser, as the person
the step belongs to, against a sandbox built from empty — and fails where a
step cannot be performed. It found one before its first screenshot:
`POST /api/rates/compute` was complete on the server, named in a comment on
`Rates.jsx`, and **called by nothing in the SPA**, so the one figure the whole
engagement produces could only be made by running a script.

Three rules it keeps:

- **It acts, and that is the point.** `walk_manuals.py` photographs without
  writing, because it runs against the live record. This one seals and
  computes, so it runs **only against a sandbox** and refuses a database that
  looks like the real one.
- **It does not do the parts that are somebody's judgment.** It signs in as
  the controller and seals, because that is a controller step being tested.
  It does **not** adopt a timesheet or sign a certification for anybody — it
  photographs the screen where a person would, which is what the runbook says
  those steps are.
- **A photograph of nothing is not a photograph.** Every shot records the
  characters on the page, and a step whose screen came up blank is a failure
  rather than a file.
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

OUT = Path("docs/runbook-walk")
CHROME = ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
          "/opt/pw-browsers/chromium/chrome-linux/chrome"]

CONTROLLER = "tom@ybi.org"
EMPLOYEE = "hruby@ybi.org"

#: (step, who, email, path, name, what it shows, actions)
#:
#: An action is (kind, argument):
#:   ("click", selector)     a control
#:   ("text", label)         a button by its visible text
#:   ("select", (sel, value)) a choice the screen makes explicit
#:   ("key", k)              the queue is keyboard-first on purpose
#:   ("wait", ms)
#:   ("expect", substring)   the page must say this, or the step failed
STEPS = [
    ("0", "Anybody", None, "/", "00-sign-in",
     "The door. Everything below is behind somebody's own account.", []),

    ("0", "Tom · controller", CONTROLLER, "/", "01-home",
     "What you hold, and what is yours to do today.", []),

    ("1", "Tom · controller", CONTROLLER, "/reconcile", "02-reconcile",
     "Schedule A-1 — the eleven points where the ledger, the P&L, the "
     "balance sheet and the payroll register have to agree. This is the "
     "gate: a rate is refused while any of them is open.",
     [("expect", "reconc")]),

    ("2", "Tom · controller", CONTROLLER, "/classify", "03-classify-sweep",
     "The queue, in Sweep. Every group carries its recommendation; nothing "
     "has been accepted on anybody's behalf.",
     [("wait", 2500)]),

    ("2", "Tom · controller", CONTROLLER, "/classify", "04-classify-focus",
     "Focus — one group at a time, the amount set large, the proposal as a "
     "single button. This is where the judgments that need thought are made.",
     [("wait", 2500), ("key", "f"), ("wait", 1200)]),

    ("3", "Tom · controller", CONTROLLER, "/rates", "05-before-seal",
     "Before sealing. Coverage and the reconciliation gate are both shown, "
     "and no rate exists — that is the guarantee, not a gap.",
     [("expect", "Seal")]),

    ("3", "Tom · controller", CONTROLLER, "/rates", "06-sealed",
     "Sealed. The hash covers every live judgment in the set. Only now does "
     "computing become possible.",
     [("text", "Seal decision set"), ("wait", 2500)]),

    ("4", "Tom · controller", CONTROLLER, "/rates", "07-computed",
     "Computed. The basis for administrative labour is chosen on the screen "
     "rather than defaulted silently — it is worth about nine points of "
     "combined rate on the same judgments — and it is recorded on the rate. "
     "A trigger refuses any rate whose seal does not match a sealed set.",
     [("select", (".ts-basis select", "POOL")),
      ("text", "Compute the rate"), ("wait", 5000)]),

    ("5", "Tom · controller", CONTROLLER, "/review/rate", "08-buildup",
     "The build-up an auditor reads. Nothing on it is computed — every "
     "figure is read from the row it was recorded in.",
     [("wait", 2000)]),

    ("P", "Heidi · employee", EMPLOYEE, "/timesheet", "09-timesheet-draft",
     "The pre-filled sheet, offered as a convenience. It says it is optional "
     "before it says anything else, and names the three complete answers. "
     "Nothing here has been adopted for anybody.",
     [("wait", 1500)]),

    ("P", "Heidi · employee", EMPLOYEE, "/certify", "10-certify",
     "Certifying is a separate act on a separate screen, and only the person "
     "whose effort it was can perform it.",
     [("wait", 1200)]),

    ("P", "Tom · controller", CONTROLLER, "/worklist", "11-worklist",
     "What is outstanding, routed to the portfolio that can act on it.",
     [("wait", 1500)]),
]


def chrome() -> str:
    for c in CHROME:
        if Path(c).exists():
            return c
    raise SystemExit("no chromium found under /opt/pw-browsers")


def guard(base: str) -> None:
    """Refuse anything that is not a sandbox.

    This walk seals and computes. Run against the live record it would
    supersede a rate somebody is relying on, and `invoice`-style
    append-only guarantees will not save a `decision_set`. The port is the
    cheap check; the expensive one is that the caller had to build the
    sandbox to have something on it.
    """
    if ":8000" in base or ":8110" in base:
        raise SystemExit(
            f"{base} is a working instance. This walk seals and computes, so "
            f"it runs only against a sandbox — see scripts/monday.sh --full.")


def act(page, kind: str, arg) -> str | None:
    try:
        if kind == "click":
            page.click(arg, timeout=6000)
        elif kind == "text":
            page.get_by_text(arg, exact=False).first.click(timeout=8000)
        elif kind == "select":
            page.select_option(arg[0], arg[1], timeout=6000)
        elif kind == "key":
            page.keyboard.press(arg)
        elif kind == "wait":
            page.wait_for_timeout(arg)
        elif kind == "expect":
            body = page.evaluate("document.body.innerText").lower()
            if arg.lower() not in body:
                return f"expected {arg!r} on the page"
        return None
    except Exception as exc:                                   # noqa: BLE001
        return f"{kind} {arg!r}: {type(exc).__name__}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:8140")
    # The queue has to be photographed *full*, before the recommendations are
    # accepted, and the seal has to be photographed *after* — so the walk runs
    # in two passes with the controller's review work in between, which is the
    # order the runbook actually describes.
    ap.add_argument("--only", default="",
                    help="comma-separated screen-name prefixes")
    args = ap.parse_args()
    password = os.environ.get("YBI_SEED_PASSWORD", "")
    if not password:
        raise SystemExit("YBI_SEED_PASSWORD is required.")
    guard(args.base)
    httpx.get(f"{args.base}/api/health", timeout=10).raise_for_status()

    OUT.mkdir(parents=True, exist_ok=True)
    taken, faults = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome(),
                                     args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000},
                                device_scale_factor=2)
        signed = "unset"
        wanted = [w.strip() for w in args.only.split(",") if w.strip()]
        for step, who, email, path, name, what, actions in STEPS:
            if wanted and not any(name.startswith(w) for w in wanted):
                continue
            if email != signed:
                page.context.clear_cookies()
                page.goto(args.base + "/", wait_until="networkidle")
                if email:
                    page.fill("input[type=email]", email)
                    page.fill("input[type=password]", password)
                    page.click("button[type=submit]")
                    page.wait_for_timeout(1800)
                signed = email
            page.goto(args.base + path, wait_until="networkidle")
            floor = 60 if email is None else 300
            try:
                page.wait_for_function(
                    f"document.body.innerText.trim().length > {floor}",
                    timeout=20000)
            except Exception:                                  # noqa: BLE001
                pass
            page.wait_for_timeout(500)

            missed = [m for m in (act(page, k, a) for k, a in actions) if m]
            shot = OUT / f"{name}.png"
            # A guidebook shows what a person sees. The classification queue
            # full-page is 20,388 pixels of scrolled list — not a screen, and
            # it buried the other eleven steps in a 31-page document. Clip to
            # a screen and a bit; the walk still reads the whole page's text
            # below, so nothing is judged on the crop.
            height = page.evaluate("document.documentElement.scrollHeight")
            page.screenshot(path=str(shot), full_page=True,
                            clip={"x": 0, "y": 0, "width": 1440,
                                  "height": min(height, 1700)})
            text = page.evaluate("document.body.innerText").strip()
            row = {"step": step, "who": who, "path": path, "name": name,
                   "shows": what, "characters": len(text),
                   "bytes": shot.stat().st_size,
                   "as": email or "signed out"}
            taken.append(row)

            # A blank screen is the failure a file-exists check cannot see.
            if len(text) < floor:
                missed.append(f"the page came up blank ({len(text)} chars)")
            if missed:
                row["faults"] = missed
                faults.append(f"{name}: " + "; ".join(missed))
                print(f"  !!  {name:22} {'; '.join(missed)}", flush=True)
            else:
                print(f"  ok  {name:22} {len(text):>6} chars  "
                      f"{shot.stat().st_size // 1024:>4} KB", flush=True)
        browser.close()

    # Merge rather than overwrite. A filtered re-run (`--only 07`) otherwise
    # replaces the record of eleven screens with the record of one, and the
    # guidebook built from it would silently lose the rest.
    manifest = OUT / "walk.json"
    prior = {r["name"]: r for r in (json.loads(manifest.read_text())
                                    if manifest.exists() else [])}
    for row in taken:
        prior[row["name"]] = row
    order = {name: i for i, (*_, name, _, _) in enumerate(STEPS)}
    merged = sorted(prior.values(), key=lambda r: order.get(r["name"], 99))
    manifest.write_text(json.dumps(merged, indent=2) + "\n")
    print(f"\n{len(taken)} screens, {len(faults)} fault(s) → {OUT}")
    for f in faults:
        print(f"  {f}")
    return 2 if faults else 0


if __name__ == "__main__":
    raise SystemExit(main())
