#!/usr/bin/env python3
"""The Monday runbook as an illustrated guide, from the walk that tested it.

    python3 scripts/runbook_guidebook.py            # HTML
    python3 scripts/runbook_guidebook.py --pdf      # and a PDF

**Every picture is a screen that was actually driven**, by
`scripts/walk_runbook.py`, against a sandbox built from empty — not a mock-up
and not a screen somebody remembered. A guide illustrated from memory goes
stale the first time a button moves, and this one carries the walk's own
manifest so a picture with nothing on it cannot pass for a picture.

The narrative is here and the screenshots are there, and neither is derived
from the other: the walk says what a screen *is*, this says what to look at
and why the step exists. Two copies of one list is the shape that produced
13.0% and 2.2% at the same moment, so the step names come from the walk.
"""

from __future__ import annotations

import argparse
import json
import html
from pathlib import Path

WALK = Path("docs/runbook-walk")
OUT = Path("docs/MONDAY_GUIDEBOOK.html")

#: What to look at on each screen, and why the step is where it is. Keyed on
#: the walk's own screen names, so a screen that stops being taken drops out
#: of the guide rather than becoming a caption over a missing picture.
NOTES = {
 "00-sign-in": (
   "Everything below is behind somebody's own account. An account on a "
   "password an administrator chose cannot write anything — not a "
   "classification, not a timesheet, not a certification — until the person "
   "changes it. The one exit from that gate is changing your own password."),
 "01-home": (
   "The landing page is assembled from what you hold, not switched on a "
   "role. The tabs are what is <em>yours to do</em>; a screen you may read "
   "but have no work on is still reachable by URL. Tom holds CONTROLLER, so "
   "he sees everything — that is what the portfolio means, not a special "
   "case."),
 "02-reconcile": (
   "<strong>Step 1, and the gate.</strong> Eleven points where the general "
   "ledger, the profit and loss, the balance sheet and the payroll register "
   "have to agree. <code>POST /api/rates/compute</code> answers 409 while "
   "any of them is open, so nothing downstream can start here. "
   "<br><br>Read <em>state</em>, never a variance of zero: both sides of "
   "most controls are <code>COALESCE(..., 0)</code>, so an empty period "
   "compares zero against zero and looks green. A control that cannot be "
   "evaluated has not passed. <br><br>The eleventh is the payroll register, "
   "and it is the one that pays for itself — it is how a $45,053 donor "
   "credit sitting in an intern wage account for a year was found, which "
   "moved the fringe rate from 22.45% to 21.90%."),
 "03-classify-sweep": (
   "<strong>Step 2.</strong> 757 cost groups, each carrying a recommendation "
   "and none of them accepted. The log beside this screen "
   "(<code>docs/CLASSIFICATION_LOG.md</code>) gives a reasoned treatment for "
   "every one, with a citation and a rationale — and a named reason where "
   "there is none. <br><br>Sweep is the dense mode for the many groups with "
   "an obvious answer. <code>j</code>/<code>k</code> move, <code>Enter</code> "
   "accepts the proposal, <code>1</code>–<code>8</code> jump to a pool. "
   "Every second saved compounds across two hundred meaningful decisions."),
 "04-classify-focus": (
   "Focus mode — <code>f</code> — for the few that need real thought. One "
   "group, the amount set large, sample memos for context, and the proposal "
   "as a single button. <br><br>Note what is <em>not</em> here: no rate, no "
   "preview of what this judgment would do to the rate. That absence is the "
   "guarantee. A reviewer will ask whether the rate was honest or "
   "reverse-engineered, and the answer has to be documentary rather than a "
   "promise."),
 "05-before-seal": (
   "Before sealing, with the queue finished. Two gates are shown and only "
   "one of them is coverage: the books must agree <em>and</em> the queue "
   "should be done. Coverage is the softer of the two — sealing below 80% is "
   "a judgment, while an open control is a refusal. <br><br>No rate exists "
   "yet. That is the design, not a gap."),
 "06-sealed": (
   "<strong>Step 3 — the judgment the whole system rests on.</strong> "
   "Sealing hashes every live classification and freezes the set. Only "
   "CONTROLLER may do it and nothing automated may do it at all: a script "
   "that sealed would put the machine's name on the assertion that the rate "
   "was not fitted to a target. <br><br>Afterwards a classification can only "
   "change by unsealing with a written reason, which supersedes any rate "
   "already computed. The card now reads from the record — it said "
   "“Before sealing” over a sealed set until this walk photographed it."),
 "07-computed": (
   "<strong>Step 4, and the step that could not be taken until this walk.</strong> "
   "<code>POST /api/rates/compute</code> was complete on the server, named "
   "in a comment on this very screen, and <strong>called by nothing in the "
   "application</strong> — so the one figure the whole engagement produces "
   "could only be made by running a script. <br><br>The basis for "
   "administrative labour is chosen here rather than defaulted silently. It "
   "is worth about nine points of combined rate on the same judgments and it "
   "is recorded on the rate, so the workpaper says which was chosen. The "
   "first version of this button sent an empty body and computed 34.82% — "
   "the default, correctly, and not the basis this engagement settled on. "
   "<br><br>Every rate carries the seal hash. A database trigger refuses one "
   "whose seal does not match a sealed set."),
 "08-buildup": (
   "<strong>Step 5.</strong> The build-up an auditor reads. "
   "<strong>Nothing on this screen is computed</strong> — every figure is "
   "read from the row it was recorded in, because a figure derived twice is "
   "one that can disagree with itself. <br><br>Read <code>pool_variance</code> "
   "and the four anchor rows. And read what it says above the figures: the "
   "rate is a working figure while anything is unfinished, and no 200.465 "
   "facilities carve-out is in it, because no facility on the record carries "
   "measured space."),
 "09-timesheet-draft": (
   "<strong>Running in parallel, at their own pace.</strong> The controller's "
   "reconstruction of a person's year, offered to the person whose work it "
   "was. <br><br>It says <strong>this is optional</strong> before it says "
   "anything else, and names three complete answers: type your own days and "
   "ignore it, adopt it and correct what is wrong, or leave it. A convenience "
   "that reads as an instruction is the one way this exercise produces "
   "forty-three signatures worth nothing. <br><br>2 CFR 200.430(i) does not "
   "require a contemporaneous record — it requires one that reflects the work "
   "performed, supported and reviewed after the fact. A reconstruction the "
   "person reads, corrects and signs meets that. One nobody ever saw does "
   "not, which is where 2025 has been sitting."),
 "10-certify": (
   "Certifying is a <strong>separate act on a separate screen</strong>. "
   "Adopting puts hours on a sheet; signing says the sheet is true. One "
   "button doing both would take a signature from somebody who had only "
   "meant to accept a starting point. <br><br>Nobody signs for anybody else. "
   "A project manager cannot sign on their team's behalf — "
   "<code>v_certification_chase</code> is a list to go and ask, never an "
   "action."),
 "11-worklist": (
   "What is outstanding, routed to the portfolio that can act on it. A "
   "CONTROLLER sees everything; an item whose portfolio nobody holds still "
   "reaches the controller rather than falling off the end. <br><br>Anybody "
   "holding a portfolio can recommend an item to somebody else with a reason "
   "— and that raises work, never a number."),
}

PHASE = {"0": "Getting in", "1": "Reconcile", "2": "Review",
         "3": "Seal", "4": "Compute", "5": "Check", "P": "In parallel"}


def build() -> str:
    rows = json.loads((WALK / "walk.json").read_text())
    missing = [r["name"] for r in rows if r["name"] not in NOTES]
    if missing:
        raise SystemExit(f"no narrative for: {', '.join(missing)}")
    parts = []
    last_phase = None
    for r in rows:
        shot = WALK / f"{r['name']}.png"
        if not shot.exists():
            raise SystemExit(f"{shot} is missing — re-run walk_runbook.py")
        phase = PHASE.get(r["step"], r["step"])
        if phase != last_phase:
            parts.append(f'<h2 class="phase">{html.escape(phase)}</h2>')
            last_phase = phase
        parts.append(f'''
<section class="step">
  <div class="meta">
    <span class="badge">{html.escape("Step " + r["step"] if r["step"].isdigit() else phase)}</span>
    <span class="who">{html.escape(r["who"])}</span>
    <code>{html.escape(r["path"])}</code>
  </div>
  <p class="what">{html.escape(r["shows"])}</p>
  <figure><img src="runbook-walk/{r['name']}.png" alt="{html.escape(r['shows'])}"></figure>
  <div class="note">{NOTES[r["name"]]}</div>
</section>''')
    return "\n".join(parts)


TEMPLATE = """<!doctype html><meta charset="utf-8">
<title>Monday, illustrated</title>
<style>
  :root {{ --ink:#1a1a1a; --muted:#5f5f5f; --rule:#d8d8d8; --accent:#1f4e5f;
           --paper:#fbfbfa; }}
  * {{ box-sizing: border-box; }}
  body {{ font: 15px/1.55 "Helvetica Neue", Helvetica, Arial, sans-serif;
         color: var(--ink); margin: 0; background: var(--paper); }}
  .wrap {{ max-width: 1180px; margin: 0 auto; padding: 40px 24px 80px; }}
  h1 {{ font-size: 30px; margin: 0 0 6px; color: var(--accent);
       letter-spacing: -.01em; }}
  .sub {{ color: var(--muted); margin: 0 0 28px; padding-bottom: 18px;
         border-bottom: 2px solid var(--accent); max-width: 80ch; }}
  h2.phase {{ font-size: 13px; text-transform: uppercase; letter-spacing: .10em;
             color: var(--accent); margin: 44px 0 12px;
             padding-bottom: 6px; border-bottom: 1px solid var(--rule); }}
  section.step {{ margin: 0 0 38px; break-inside: avoid; }}
  .meta {{ display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap;
          margin-bottom: 6px; }}
  .badge {{ background: var(--accent); color: #fff; font-size: 11px;
           font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
           padding: 3px 8px; border-radius: 3px; }}
  .who {{ font-weight: 700; }}
  code {{ background: #eceeef; padding: 1px 5px; border-radius: 3px;
         font-size: .88em; }}
  .what {{ margin: 0 0 12px; max-width: 85ch; }}
  figure {{ margin: 0 0 14px; border: 1px solid var(--rule); border-radius: 6px;
           overflow: hidden; background: #fff;
           box-shadow: 0 1px 3px rgba(0,0,0,.07); }}
  img {{ display: block; width: 100%; }}
  .note {{ border-left: 3px solid var(--accent); padding: 2px 0 2px 14px;
          color: #333; max-width: 88ch; }}
  .banner {{ background: #f2f5f6; border-left: 3px solid var(--accent);
            padding: 14px 18px; margin: 0 0 30px; max-width: 88ch; }}
  footer {{ margin-top: 50px; padding-top: 18px; border-top: 1px solid var(--rule);
           color: var(--muted); font-size: 13px; max-width: 88ch; }}
  @media print {{ body {{ background: #fff; }} .wrap {{ padding: 0; }}
                  section.step {{ page-break-inside: avoid; }} }}
</style>
<div class="wrap">
<h1>Monday, illustrated</h1>
<p class="sub">Every screen below was driven by <code>scripts/walk_runbook.py</code>
against a sandbox built from an empty database — signed in as the person the
step belongs to, clicking the controls a person clicks. Nothing here is a
mock-up and nothing was photographed from the live record.</p>

<div class="banner">
<p style="margin:0 0 8px"><strong>The walk found one thing before its first
screenshot.</strong> <code>POST /api/rates/compute</code> was complete on the
server, named in a comment on the rates screen, and <strong>called by nothing
in the application</strong> — so the one figure the whole engagement exists to
produce could only be made by somebody running a script. Step 4 could not be
performed. It can now.</p>
<p style="margin:0">A runbook nobody has walked is a list of things somebody
believes.</p>
</div>

{body}

<footer>
<p><strong>What is deliberately missing from these pictures.</strong> No rate
appears on any classification screen. No timesheet was adopted and no
certification signed — those belong to the forty-three people whose effort it
was, and this walk photographs the screens where they would act rather than
acting for them. The sealing and the computing <em>were</em> performed,
because they are controller steps being tested, and they ran against a
throwaway database that was dropped afterwards.</p>
<p>Regenerate: <code>scripts/walk_runbook.py</code> then
<code>scripts/runbook_guidebook.py</code>. The walk fails on a step that
cannot be performed or a screen that comes up blank, so a picture of nothing
cannot pass for a picture.</p>
</footer>
</div>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", action="store_true")
    args = ap.parse_args()
    OUT.write_text(TEMPLATE.format(body=build()))
    print(f"wrote {OUT}")
    if args.pdf:
        from playwright.sync_api import sync_playwright
        pdf = OUT.with_suffix(".pdf")
        chrome = next(c for c in
                      ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome"]
                      if Path(c).exists())
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=chrome, args=["--no-sandbox"])
            pg = b.new_page()
            pg.goto(OUT.resolve().as_uri(), wait_until="networkidle")
            pg.pdf(path=str(pdf), format="Letter", print_background=True,
                   margin={"top": "0.5in", "bottom": "0.5in",
                           "left": "0.5in", "right": "0.5in"})
            b.close()
        print(f"wrote {pdf} ({pdf.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
