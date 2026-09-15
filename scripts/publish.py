#!/usr/bin/env python3
"""Everything that leaves the building, in one run.

    DATABASE_URL=... YBI_SEED_PASSWORD=... python3 scripts/publish.py \
        [--base http://127.0.0.1:8000] [--out docs/publications]

The rate publications, the Form 990, the auditor's report, the audit package,
the labour evidence, and the America Makes invoices reissued on the
negotiated rate — each with the amendment memorandum that says why and the
acceptance form NCDMM signs.

**Nothing here is blocked by a missing signature or a missing document.**
That is `082`'s design rather than a shortcut: an invoice can be regenerated
and a workbook produced at any time, because testing against real figures is
ordinary work and a machine that refused it is one people route around. What
changes is what the paper *says*. So every document in this set carries the
certification band in whichever direction is true, and every one states what
is unfinished above its figures.

Three rules it keeps:

  * **Through the doors people use.** Every workbook is fetched from the
    route the screen calls, so a figure in this set and the same figure on
    the screen cannot disagree. A second assembly here would be a second
    implementation of each document, free to drift — which is the defect
    most of `CLAUDE.md` is about.
  * **It writes nothing to the cost record.** No seal, no rate, no
    restatement, no acceptance. A publication run that recorded a position
    would be the machine putting YBI's name on a claim.
  * **The manifest is the point.** Every file, its SHA-256 and what it says
    is unfinished — so a digest that moves means a figure moved, and a reader
    can tell a set produced before the square footage arrived from one
    produced after.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import one, query                                  # noqa: E402
from app.foundation import EMAIL                                # noqa: E402

BOLD, OK, WARN, FAIL, END = "\033[1m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"

PERIOD = "2025"
FILES: list[dict] = []
NOTES: list[str] = []


def head(text: str) -> None:
    print(f"\n{BOLD}{text}{END}", flush=True)


def wrote(path: Path, what: str, caveats: list[str]) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    FILES.append({"file": path.name, "what": what, "bytes": path.stat().st_size,
                  "sha256": digest, "says_unfinished": caveats})
    print(f"  {OK}ok{END}   {path.name:52} {path.stat().st_size:>9,} bytes")


def note(text: str) -> None:
    NOTES.append(text)
    print(f"  {WARN}·{END}    {text}")


def bad(text: str) -> None:
    NOTES.append("FAILED: " + text)
    print(f"  {FAIL}!!{END}   {text}")


def sign_in(base: str) -> httpx.Client:
    pw = os.environ.get("YBI_SEED_PASSWORD", "")
    if not pw:
        raise SystemExit("YBI_SEED_PASSWORD is required.")
    c = httpx.Client(base_url=base, timeout=600, follow_redirects=False)
    email = EMAIL["tom"]
    for candidate in (pw + "-own!", pw, pw.rstrip("!") + "-own!"):
        r = c.post("/api/auth/login", json={"email": email, "password": candidate})
        if r.status_code == 200:
            if r.json().get("must_set_password"):
                c.post("/api/auth/password",
                       json={"current_password": candidate,
                             "new_password": pw.rstrip("!") + "-own!"})
            return c
    raise SystemExit(f"could not sign in as {email} ({r.status_code}). "
                     f"This run reads through the API so that every figure "
                     f"comes from the route a screen calls.")


def fetch(c: httpx.Client, path: str, out: Path, what: str,
          caveats: list[str]) -> bool:
    r = c.get(path)
    if r.status_code != 200:
        bad(f"{path} answered {r.status_code} — {str(r.text)[:120]}")
        return False
    out.write_bytes(r.content)
    wrote(out, what, caveats)
    return True


# ── what the record says is unfinished ───────────────────────────────

def _fmt_when(value) -> str:
    return f"Invoice dated {value:%d %b %Y}." if value else ""


def certification() -> dict:
    row = one("""SELECT period, certified, certified_by, certified_at,
                        why_not, outstanding
                   FROM v_rate_certified WHERE period = %s""", (PERIOD,))
    return row or {}


def walk_caveats() -> list[str]:
    """The walk's own unfinished steps, in its own words.

    Not a list written here. A publication set that described the state of
    the record in prose somebody typed is the hand-kept map, printed and
    posted.
    """
    return [f"{r['step']} — {r['detail']}"
            for r in query("""SELECT step, state, detail FROM v_audit_walk
                               WHERE period = %s AND state <> 'DONE'
                               ORDER BY seq""", (PERIOD,))]


# ── the amendment papers, per award ──────────────────────────────────

def amendment_papers(c, out_dir: Path, caveats: list[str]) -> None:
    """One memo and one form per award that has a standing restatement.

    **Fetched from the routes the screen calls**, like every workbook above.
    The assembly lives in `app/routers/restate.py`; a copy of it here would
    be a second implementation of the same paper, free to drift from the one
    a controller downloads — which is the defect most of `CLAUDE.md` is
    about, and which this function was until the screen got its door.
    """
    awards = query("""SELECT DISTINCT award_id FROM v_restatement
                       WHERE period = %s AND status = 'PROPOSED'
                         AND award_id IS NOT NULL
                       ORDER BY award_id""", (PERIOD,))
    if not awards:
        note("no restatement is standing as a claim, so there is nothing to "
             "put an amendment memorandum against. `POST /api/restate` is "
             "what makes one, and it is a judgment.")
        return

    for row in awards:
        award_id = row["award_id"]
        for which, name, what in (
                ("memo", f"amendment-memo-{award_id}.pdf",
                 f"why {award_id}'s invoices are being reissued, and the "
                 f"clause it is made under"),
                ("acceptance", f"acceptance-{award_id}.pdf",
                 f"what NCDMM signs for {award_id} — both directions, "
                 f"never netted")):
            r = c.get(f"/api/restate/award/{award_id}/{which}?period={PERIOD}")
            if r.status_code != 200:
                bad(f"{award_id} {which} answered {r.status_code}: "
                    f"{r.text[:200]}")
                continue
            f = out_dir / name
            f.write_bytes(r.content)
            wrote(f, what, caveats)

        clause = one("""SELECT term_value FROM award_term
                         WHERE award_id = %s AND term_key = 'Change of basis'""",
                     (award_id,)) or {}
        if not clause.get("term_value"):
            note(f"{award_id}: no change-of-basis clause on the record, so the "
                 f"memorandum asks NCDMM to name the instrument instead of "
                 f"citing one.")


def _readme(m: dict) -> str:
    """The manifest, as a page. Nothing here is composed twice."""
    out = [f"# YBI {m['period']} publication set", "",
           f"Produced {m['produced']} by `scripts/publish.py`. Every figure is",
           "read from the row it was recorded in; nothing in this set was",
           "written to the cost record.", ""]
    if m["certified"]:
        out += [f"**CERTIFIED** — {m['certified_by']}. Every document says so",
                "on its own face.", ""]
    else:
        out += ["**NOT CERTIFIED** — nobody has put their name to the rate",
                f"these figures rest on. {m['why_not']}",
                "",
                "Nothing here is blocked by that. These are working documents",
                "and each one says so above its figures, which is `082`'s rule:",
                "a document silent either way leaves the reader to assume, and",
                "the assumption made about a figure on a letterhead is the",
                "generous one.", ""]
    out += ["## The rate these rest on", "",
            "| | rate | base | administrative labour | seal |",
            "| --- | ---: | --- | --- | --- |"]
    for r in m["rates"]:
        out.append(f"| {r['kind']} | {float(r['rate']) * 100:.2f}% | "
                   f"{r['base']} | {r['basis']} | `{str(r['seal'])[:12]}` |")
    out += ["", "## What is not finished", ""]
    out += [f"- {c}" for c in m["unfinished"]] or ["- Nothing."]
    out += ["", "## The documents", "",
            "| file | what it is | bytes | sha256 |", "| --- | --- | ---: | --- |"]
    for f in m["files"]:
        out.append(f"| `{f['file']}` | {f['what']} | {f['bytes']:,} | "
                   f"`{f['sha256'][:12]}` |")
    out += ["",
            "Rendering is deterministic, so a digest that moves means a figure",
            "moved — which is how a set produced before the square footage",
            "arrived is told apart from one produced after.", ""]
    if m["notes"]:
        out += ["## Notes from the run", ""] + [f"- {n}" for n in m["notes"]] + [""]
    return "\n".join(out)


# ── the run ──────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default="docs/publications")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    c = sign_in(args.base)

    cert = certification()
    caveats = walk_caveats()

    head(f"Publishing {PERIOD}")
    if cert.get("certified"):
        print(f"  the rate is certified — {cert.get('certified_by')}")
    else:
        print(f"  {WARN}the rate carries no signature{END} — "
              f"{cert.get('why_not') or 'nobody has put their name to it'}")
        print("  Nothing below is blocked by that. Every document says so on "
              "its own face.")
    print(f"  {len(caveats)} step(s) of the walk are not done, and every "
          f"document carries them:")
    for line in caveats:
        print(f"    · {line[:110]}")

    head("The rate")
    rates = query("""SELECT kind, rate, pool_amount, base_type, base_amount,
                            status, admin_labour_basis, seal_hash
                       FROM rate WHERE period = %s AND status <> 'SUPERSEDED'
                      ORDER BY kind""", (PERIOD,))
    for r in rates:
        print(f"  {r['kind']:20} {Decimal(str(r['rate'])) * 100:>7.2f}%   "
              f"pool {Decimal(str(r['pool_amount'])):>14,.2f}  over "
              f"{Decimal(str(r['base_amount'])):>14,.2f}  {r['base_type']}")
    if not rates:
        note("no rate on file — the build-up will say so rather than not be "
             "produced.")
    fetch(c, "/api/export/rate-buildup", out_dir / "rate-buildup.xlsx",
          "the rate, the pool under it and the seal it hangs off", caveats)

    head("The return")
    fetch(c, "/api/export/form-990", out_dir / "form-990-part-ix.xlsx",
          "Form 990 Part IX, functional allocation as classified", caveats)

    head("The report")
    fetch(c, "/api/export/auditors-report", out_dir / "auditors-report.xlsx",
          "what the engagement asserts and what proves each assertion", caveats)
    fetch(c, "/api/export/audit-package", out_dir / "audit-package.xlsx",
          "the whole cost record, every sheet", caveats)

    head("The labour evidence")
    fetch(c, "/api/reports/timesheet", out_dir / "timesheet-report.xlsx",
          "the distribution behind the fringe base, and who has certified",
          caveats)

    head("The invoices, as they would be reissued")
    invoices = query("""SELECT invoice_id, invoice_number, objective_id
                          FROM invoice
                         WHERE period = %s AND objective_id IN (
                               SELECT objective_id FROM v_restatement
                                WHERE period = %s AND status = 'PROPOSED')
                         ORDER BY invoice_number""", (PERIOD, PERIOD))
    got = 0
    for inv in invoices:
        r = c.get(f"/api/reports/invoice/{inv['invoice_id']}")
        if r.status_code != 200:
            bad(f"invoice {inv['invoice_number']} answered {r.status_code}")
            continue
        f = out_dir / f"invoice-{inv['invoice_number']}.pdf"
        f.write_bytes(r.content)
        wrote(f, f"invoice {inv['invoice_number']} on {inv['objective_id']}, "
                 f"rendered from the register", caveats)
        got += 1
    if not got:
        note("no invoice on an objective with a standing restatement — "
             "nothing to reissue.")

    head("The papers that go with them")
    amendment_papers(c, out_dir, caveats)

    head("The manifest")
    manifest = {
        "period": PERIOD,
        "produced": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "certified": bool(cert.get("certified")),
        "certified_by": cert.get("certified_by"),
        "why_not": cert.get("why_not"),
        "unfinished": caveats,
        "rates": [{"kind": r["kind"], "rate": str(r["rate"]),
                   "base": r["base_type"], "basis": r["admin_labour_basis"],
                   "seal": r["seal_hash"]} for r in rates],
        "files": FILES,
        "notes": NOTES,
    }
    path = out_dir / "MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    print(f"  {OK}ok{END}   {path.name:52} {len(FILES)} file(s) listed")

    # A person opening the folder sees forty-four files and a JSON. The
    # sentence they want is on every row of that JSON already, so the README
    # is **rendered from the manifest** rather than written: a hand-kept
    # description of a generated set is the map that cannot be checked, and
    # it would go stale on the first run that produced a different set.
    readme = out_dir / "README.md"
    readme.write_text(_readme(manifest))
    print(f"  {OK}ok{END}   {readme.name:52} rendered from the manifest")

    failed = [n for n in NOTES if n.startswith("FAILED")]
    head(f"{len(FILES)} document(s) into {out_dir}")
    if failed:
        print(f"  {FAIL}{len(failed)} did not produce{END}")
        return 1
    print("  Every one states whether the rate is signed and what is "
          "unfinished.\n  Nothing was written to the cost record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
