#!/usr/bin/env python3
"""Every screen, as every person, in a real browser — and what the network did.

    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/drive_ui.py \
        --base http://127.0.0.1:8141

`review_system.py` asks whether every route answers, as everybody, at the
**API** level. `walk_manuals.py` photographs screens. Neither watches what a
screen actually does when a person opens it, and that is where the last three
defects lived:

- a screen calling a route that 404s and swallowing it with `.catch(() => {})`
- a screen rendering an error object into a table and taking the page down
- a capability with no screen at all

So this opens each screen as each actor and records **every request the page
made and what came back**, every console error, and whether anything was
drawn — then photographs it. A 403 is not a fault here: a screen reachable by
URL that refuses somebody who may not read it is the system working, and the
nav is what decides whether it is *offered*. A **404 or a 5xx is always a
fault**, because no screen should ask for a route that is not there.

It writes nothing. Every action is a page load.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

OUT = Path("docs/ui-sweep")
CHROME = ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
          "/opt/pw-browsers/chromium/chrome-linux/chrome"]

#: **Everybody, read from the record.** A hand-kept list of who exists was
#: wrong on its first run — it named an account that does not exist and
#: called a controller an employee — which is the defect this repository
#: keeps finding in its own tests. `v_actor_access` already knows.
def actors() -> list[tuple[str | None, str]]:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.db import open_pool, query
    open_pool()
    rows = query("""SELECT email, role, portfolios, may_read_record, may_seal,
                           employee_key
                      FROM v_actor_access WHERE is_active
                     ORDER BY role, email""")
    out: list[tuple[str | None, str]] = [(None, "signed out")]
    for r in rows:
        # `portfolios` arrives as Postgres's array literal, a *string*.
        # `list()` over it gave one entry per character and every label read
        # `c+e+l+l+n+o+o+r+r+t`. Read the shape, do not assume it.
        raw = r["portfolios"]
        held = ([x.strip() for x in str(raw).strip("{}").split(",") if x.strip()]
                if not isinstance(raw, (list, tuple)) else list(raw))
        what = r["role"].replace("_", " ").lower()
        if held:
            what += " · " + "+".join(sorted(held)).lower()
        if r["employee_key"]:
            what += " · on the payroll"
        out.append((r["email"], what))
    return out


#: Every route in the SPA. Derived below from App.jsx rather than kept here,
#: because a hand-kept map of what the code does was wrong four times in one
#: run of the system review.
def spa_routes(root: Path) -> list[str]:
    import re
    src = (root / "web" / "src" / "App.jsx").read_text()
    paths = set(re.findall(r'<Route\s+path="([^"*]+)"', src))
    return sorted(p if p.startswith("/") else "/" + p for p in paths
                  if "/:" not in p)


def chrome() -> str:
    for c in CHROME:
        if Path(c).exists():
            return c
    raise SystemExit("no chromium under /opt/pw-browsers")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:8141")
    ap.add_argument("--shots", action="store_true",
                    help="photograph every screen, not only the faulted ones")
    args = ap.parse_args()
    password = os.environ.get("YBI_SEED_PASSWORD", "")
    if not password:
        raise SystemExit("YBI_SEED_PASSWORD is required.")
    httpx.get(f"{args.base}/api/health", timeout=10).raise_for_status()

    root = Path(__file__).resolve().parent.parent
    routes = spa_routes(root)
    ACTOR_LIST = actors()
    print(f"{len(routes)} screens x {len(ACTOR_LIST)} people\n")
    OUT.mkdir(parents=True, exist_ok=True)
    rows, faults = [], []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome(),
                                     args=["--no-sandbox"])
        for email, who in ACTOR_LIST:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            seen: list[dict] = []
            errors: list[str] = []
            page.on("response", lambda r: seen.append(
                {"url": r.url, "status": r.status}) if "/api/" in r.url else None)
            page.on("console", lambda m: errors.append(m.text)
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

            page.goto(args.base + "/", wait_until="networkidle")
            if email:
                page.fill("input[type=email]", email)
                page.fill("input[type=password]", password)
                page.click("button[type=submit]")
                page.wait_for_timeout(1800)

            # What the nav offers this person — the screens that are *theirs*.
            offered = set(page.eval_on_selector_all(
                "nav a[href], a[href^='/']",
                "els => els.map(e => new URL(e.href).pathname)") or [])

            for path in routes:
                seen.clear(); errors.clear()
                page.goto(args.base + path, wait_until="networkidle")
                try:
                    page.wait_for_function(
                        "document.body.innerText.trim().length > 40",
                        timeout=12000)
                except Exception:                              # noqa: BLE001
                    pass
                page.wait_for_timeout(400)
                text = page.evaluate("document.body.innerText").strip()

                calls = [c for c in seen if "/api/" in c["url"]]
                bad = [c for c in calls if c["status"] >= 500
                       or c["status"] == 404]
                refused = [c for c in calls if c["status"] == 403]
                row = {"who": who, "as": email or "signed out", "path": path,
                       "offered_in_nav": path in offered,
                       "calls": len(calls), "characters": len(text),
                       "not_found_or_fault": [f"{c['status']} {c['url'].split('/api/')[-1]}"
                                              for c in bad],
                       "refused": len(refused),
                       "refused_paths": sorted({c["url"].split("/api/")[-1]
                                                .split("?")[0]
                                                for c in refused}),
                       "console_errors": errors[:4]}
                rows.append(row)

                why = []
                if bad:
                    why.append("asked for " + ", ".join(row["not_found_or_fault"]))
                # **A 401 signed out and a 403 on a screen you may not read
                # are the system working, not faults.** The browser logs a
                # generic "Failed to load resource" for both, so counting
                # every console error made twenty-three correct refusals look
                # like defects — which is the shape that teaches a reader to
                # ignore the list. Status is analysed separately above; only
                # errors that are *not* an expected refusal count here.
                real = [e for e in errors
                        if "Failed to load resource" not in e
                        or not any(f" {c} " in f" {e} " for c in ("401", "403"))]
                if real:
                    why.append(f"console: {real[0][:90]}")
                # A signed-out visitor correctly gets the sign-in screen; an
                # actor who reaches a screen and is shown nothing at all is
                # the failure a status code cannot see.
                if email and len(text) < 40:
                    why.append(f"drew nothing ({len(text)} chars)")
                if why:
                    row["faults"] = why
                    faults.append(f"{who:26} {path:18} " + "; ".join(why))
                    print(f"  !!  {who:26} {path:18} {'; '.join(why)}",
                          flush=True)

                if args.shots or why:
                    name = f"{(email or 'anon').split('@')[0]}{path.replace('/', '_')}"
                    page.screenshot(path=str(OUT / f"{name}.png"),
                                    full_page=True,
                                    clip={"x": 0, "y": 0, "width": 1440,
                                          "height": 1400})
            print(f"  ok  {who:26} {len(routes)} screens", flush=True)
            page.close()
        browser.close()

    # **The nav is not a security boundary, and it is a promise.** Never
    # offer a tab that will answer 403 — and never hide one the API would
    # allow. Both directions are the same defect: the screen and the server
    # disagreeing about who you are. Nothing had ever checked it from the
    # browser.
    nav = []
    for r in rows:
        if r["as"] == "signed out":
            continue
        if r["offered_in_nav"] and r["refused"]:
            nav.append(f"{r['who']:30} {r['path']:14} is offered in the nav "
                       f"and refuses: {', '.join(r['refused_paths'])}")
    if nav:
        print("\n  the nav and the API disagree:")
        for n in nav:
            print(f"    {n}")
        faults.extend(nav)

    (OUT / "sweep.json").write_text(json.dumps(rows, indent=2) + "\n")
    by_actor = defaultdict(int)
    for r in rows:
        by_actor[r["who"]] += 1
    print(f"\n{len(rows)} screen-visits across {len(ACTOR_LIST)} people, "
          f"{len(faults)} fault(s)")
    for f in faults:
        print(f"  {f}")
    print(f"\n{OUT / 'sweep.json'}")
    return 2 if faults else 0


if __name__ == "__main__":
    raise SystemExit(main())
