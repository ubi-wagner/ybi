#!/usr/bin/env python3
"""Photograph every screen against the loaded 2025 record, and say what is on it.

    YBI_SWEEP_PASSWORD=... python3 scripts/sweep_screens.py --base http://127.0.0.1:8092

`drive_ui.py` asks whether a screen *works* — no 404, no 5xx, no console
error, nothing offered in the nav that refuses the person it is offered to.
That is a different question from whether a screen is any use to the
controller closing 2025, which is what this answers: for each screen, what
it actually renders against a record with the whole year in it.

So it records, per screen: the headings, how many figures are on the page,
how many of those figures are clickable through to anything, how many
tables and rows, what drawers or modals it can open, and every empty state
it shows. That inventory is the input to the audit UI — a screen with
forty figures and no links is a screen where the auditor's next question
has no answer on it.

Three rules borrowed from the sweep it sits beside: a 403 is not a fault
and a 401 signed out is not a fault, a 404 or a 5xx always is, and the
roster comes from `v_actor_access` rather than a list kept here by hand.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
OUT = Path("docs/screen-sweep")

#: Read from App.jsx rather than kept here: a hand-kept list of screens was
#: wrong four times in one run of the system review.
def screens() -> list[tuple[str, str]]:
    src = (Path(__file__).resolve().parent.parent
           / "web" / "src" / "App.jsx").read_text()
    block = src[src.index("const ALL_TABS"):src.index("function tabsFor")]
    return [(m[0], m[1]) for m in
            re.findall(r'\["(/[^"]*)",\s*"([^"]+)"', block)]


def look(page) -> dict:
    """What is on the screen, counted rather than described.

    **The first version of this counted nothing and was believed for about a
    minute.** It matched a whole cell against a regex requiring two decimal
    places, and the review screens print whole dollars — `1,497,879` where
    the record holds `1,497,879.12` — so it reported *zero figures* on the
    rate build-up and the reconciliation, which are made of nothing else. An
    instrument that reads zero on a screen full of money is wrong about the
    instrument, not about the screen; this repository has had four of those
    and every one was believed until somebody looked.

    So it walks text nodes rather than whole cells, takes a figure with or
    without decimals and a percentage as well, and asks of each one whether
    it or anything above it is something you can click.
    """
    return page.evaluate("""() => {
      const t = (s) => Array.from(document.querySelectorAll(s));
      // A figure: 1,234 / 1,234.56 / $(1,234.56) / 21.90%
      const money = /(^|[\s$(])-?\d[\d,]*(\.\d+)?%?([\s)]|$)/;
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const nav = document.querySelector('nav');
      const figures = [];
      while (walker.nextNode()) {
        const n = walker.currentNode, s = (n.textContent || '').trim();
        if (!s || s.length > 60 || !money.test(s)) continue;
        if (!/\d/.test(s)) continue;
        const el = n.parentElement;
        if (!el || (nav && nav.contains(el))) continue;
        const clickable = !!el.closest('a,button,[role=button],[data-href],.clickable');
        figures.push({ text: s.slice(0, 28), clickable });
      }
      return {
        headings: t('h1,h2,.card-title,.page-head-title')
                    .map(e => (e.textContent||'').trim()).filter(Boolean).slice(0, 14),
        figures: figures.length,
        figures_linked: figures.filter(f => f.clickable).length,
        sample: figures.slice(0, 5).map(f => f.text),
        tables: t('table').length,
        rows: t('tbody tr').length,
        buttons: t('button').map(e => (e.textContent||'').trim())
                   .filter(x => x && x.length < 40),
        empty_states: t('.empty,.empty-title').map(e => (e.textContent||'').trim())
                        .filter(Boolean).slice(0, 6),
        drew: document.body.innerText.trim().length,
      };
    }""")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8092")
    ap.add_argument("--as", dest="who", default="tmetzinger@ybi.org")
    ap.add_argument("--shots", action="store_true")
    args = ap.parse_args()
    pw = os.environ.get("YBI_SWEEP_PASSWORD", "")
    if not pw:
        print("YBI_SWEEP_PASSWORD is required.", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    report: list[dict] = []

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        ctx = b.new_context(viewport={"width": 1500, "height": 1100})
        page = ctx.new_page()
        bad: list[tuple[int, str]] = []
        page.on("response", lambda r: bad.append((r.status, r.url))
                if "/api/" in r.url and (r.status == 404 or r.status >= 500) else None)

        page.goto(args.base, wait_until="networkidle")
        page.fill("input[type=email]", args.who)
        page.fill("input[type=password]", pw)
        page.click("button[type=submit]")
        page.wait_for_timeout(1500)
        # The *inputs*, not the phrase. Matching on text found "Choose your
        # own password" in the manual panel on Home and then waited thirty
        # seconds for a box that was never going to be there.
        boxes = page.locator("input[type=password]")
        if boxes.count() >= 2:
            boxes.nth(0).fill(pw)
            for i in range(1, boxes.count()):
                boxes.nth(i).fill(pw + "-own")
            page.click("button[type=submit]")
            page.wait_for_timeout(2000)

        for path, label in screens():
            before = len(bad)
            page.goto(args.base + path, wait_until="networkidle")
            page.wait_for_timeout(1400)
            seen = look(page)
            seen.update(path=path, label=label,
                        faults=[f"{s} {u.split('/api')[-1]}" for s, u in bad[before:]])
            if args.shots:
                page.screenshot(path=str(OUT / f"{label.lower().replace(' ','-')}.png"),
                                full_page=True)
            report.append(seen)
            print(f"  {label:<14} figures {seen['figures']:>4}  linked "
                  f"{seen['figures_linked']:>4}  rows {seen['rows']:>5}  "
                  f"{'FAULT ' + ','.join(seen['faults']) if seen['faults'] else ''}")
        b.close()

    (OUT / "sweep.json").write_text(json.dumps(report, indent=1))
    figs = sum(r["figures"] for r in report)
    linked = sum(r["figures_linked"] for r in report)
    faults = sum(len(r["faults"]) for r in report)
    print(f"\n{len(report)} screens · {figs} figures on them · {linked} "
          f"({100*linked//max(figs,1)}%) clickable to anything · {faults} fault(s)")
    print(f"{OUT}/sweep.json")
    return 1 if faults else 0


if __name__ == "__main__":
    raise SystemExit(main())
