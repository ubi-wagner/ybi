#!/usr/bin/env python3
"""A full pass over the system, as every kind of person who uses it.

Six dimensions, because a system can be sound on one and broken on another
and the failure modes do not look alike:

  CONNECTIVITY   every route answers, and answers something other than 500
  CAPABILITY     every person can reach everything their nav offers them,
                 and nothing it does not
  FUNCTIONALITY  the screens that should carry data carry data
  AUDITABILITY   every change names who made it and the session it was in
  CONTINUITY     a figure can be walked to the ledger and back again
  PROPORTION     a change moves what it should, by the amount it should,
                 and moves nothing else

The point is not a green light. It is a list of findings with enough in each
to act on, and a count that can be compared to the last run — which is why
this writes a report rather than printing a pass.

    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/review_system.py \\
        [--base http://127.0.0.1:8000] [--out docs/SYSTEM_REVIEW.md]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.foundation import EMAIL  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

#: Severity, most serious first. A FAULT is the system not working; a GAP is
#: it working over data nobody has supplied yet, which is a different
#: conversation and must not be reported as the same thing.
FAULT, GAP, NOTE = "FAULT", "GAP", "NOTE"

findings: list[dict] = []
facts: dict[str, object] = {}


def finding(dimension: str, severity: str, what: str, detail: str = "",
            fix: str = "") -> None:
    findings.append({"dimension": dimension, "severity": severity,
                     "what": what, "detail": detail, "fix": fix})
    mark = {FAULT: "FAULT", GAP: "gap  ", NOTE: "note "}[severity]
    print(f"  {mark}  [{dimension}] {what}", flush=True)
    if detail:
        print(f"         {detail}", flush=True)


def ok(msg: str) -> None:
    print(f"  ok     {msg}", flush=True)


# ── Signing in as everybody ──────────────────────────────────────────

#: The people this system is for. Not a list of roles — a list of jobs, and
#: the difference matters: two of these hold the same rank and do different
#: work, and one holds the highest rank and the least authority over cost.
WHO = [
    ("eric.c.wagner@gmail.com", "Eric", "SYSTEM_ADMIN",
     "stands the software up; reads the record only on a written grant"),
    ("bewing@ybi.org", "Barb", "ORG_ADMIN",
     "hands out access; holds no portfolio and judges no cost"),
    (EMAIL["tom"], "Tom", "CONTROLLER",
     "classifies, seals, computes the rate, restates"),
    ("sgaffney@ybi.org", "Stephanie", "CONTROLLER+ALL",
     "project manager, holding every portfolio for the 2025 push"),
    ("hruby@ybi.org", "Heidi", "CONTROLLER+ALL",
     "facilities and inventory, holding every portfolio for the 2025 push"),
    ("auditor@ybi.org", "Auditor", "AUDITOR",
     "reads everything, writes nothing"),
]


def sign_in(base: str, email: str, password: str) -> httpx.Client | None:
    c = httpx.Client(base_url=base, timeout=120, follow_redirects=False)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        c.close()
        return None
    return c


# ── 1. Connectivity ──────────────────────────────────────────────────

#: Path parameters this probe can fill from real rows. A route whose
#: parameter cannot be filled is reported rather than skipped silently — a
#: route nobody can call is a route nobody is testing.
def _samples(c: httpx.Client, admin: httpx.Client) -> dict[str, str]:
    """Real values for the path parameters, read off real rows.

    An earlier version sampled `/api/contracts/codes` and `/api/rates/sets`,
    neither of which is a route, so two parameters went unfilled and every
    route taking them was quietly left unprobed. A probe that cannot fill a
    parameter says so now rather than skipping in silence, which is how that
    was noticed.
    """
    def first(client: httpx.Client, path: str, key: str,
              sub: str | None = None):
        r = client.get(path)
        if r.status_code != 200:
            return None
        # A 200 that is not JSON is a finding in itself, and used to be one:
        # the SPA catch-all answered every unmatched /api path with
        # index.html, so a removed endpoint looked healthy to anything
        # checking a status code.
        if "json" not in r.headers.get("content-type", ""):
            finding("CONNECTIVITY", FAULT,
                    f"GET {path} answers 200 with "
                    f"{r.headers.get('content-type', 'no content type')}",
                    "An /api path must answer JSON or 404. Answering the "
                    "SPA's HTML makes a dropped route indistinguishable from "
                    "a working one.")
            return None
        body = r.json()
        rows = body if isinstance(body, list) else (body.get(sub) if sub else None)
        if rows is None and isinstance(body, dict):
            for v in body.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    rows = v
                    break
        if not rows or not isinstance(rows[0], dict):
            return None
        value = rows[0].get(key)
        return str(value) if value is not None else None

    return {
        "evidence_id": first(c, "/api/documents/library", "evidence_id",
                             "documents"),
        "invoice_id": first(c, "/api/reports/invoices", "invoice_number",
                            "invoices"),
        "award_id": first(c, "/api/awards", "award_id", "awards"),
        # The roster is the administrator's screen. Asking for it as the
        # controller returns a correct 403 and no sample.
        "actor_id": first(admin, "/api/auth/actors", "actor_id"),
        "employee_key": first(c, "/api/contracts/employees", "employee_key",
                              "employees"),
        "objective_id": first(c, "/api/contracts/charge-codes", "objective_id",
                              "codes"),
        "period": "2025",
        "kind": "rate-buildup",
    }


def connectivity(base: str, clients: dict[str, httpx.Client]) -> None:
    print("\nCONNECTIVITY — every route answers, as everybody")
    spec = httpx.get(f"{base}/api/openapi.json", timeout=60).json()
    probe = clients["Tom"]
    samples = _samples(probe, clients["Barb"])
    facts["samples"] = {k: v for k, v in samples.items() if v}

    unfilled = [k for k, v in samples.items() if v is None]
    if unfilled:
        finding("CONNECTIVITY", NOTE,
                f"{len(unfilled)} path parameters had no row to fill them",
                f"{', '.join(sorted(unfilled))} — routes taking these were not "
                f"probed, so they are untested rather than passing.")

    results: dict[str, dict[str, int]] = defaultdict(dict)
    probed = skipped = 0
    for path, ops in sorted(spec["paths"].items()):
        if "get" not in ops:
            continue
        params = re.findall(r"\{(\w+)\}", path)
        if any(samples.get(p) is None for p in params):
            skipped += 1
            continue
        url = path
        for p in params:
            url = url.replace(f"{{{p}}}", str(samples[p]))
        probed += 1
        for name, c in clients.items():
            r = c.get(url)
            results[path][name] = r.status_code
            if r.status_code >= 500:
                finding("CONNECTIVITY", FAULT,
                        f"GET {path} answers {r.status_code} for {name}",
                        r.text[:200].replace("\n", " "))
    facts["routes_probed"] = probed
    facts["routes_skipped"] = skipped
    facts["route_matrix"] = {p: v for p, v in results.items()}
    ok(f"{probed} GET routes probed as {len(clients)} people "
       f"({probed * len(clients)} calls); {skipped} skipped for want of a row")
    return results


# ── 2. Capability — the nav against what the API allows ──────────────

def _tabs() -> list[tuple[str, str, str, str | None]]:
    """The nav, read out of App.jsx rather than restated here.

    A list kept in two places is a list that disagrees with itself, and the
    whole point of this dimension is whether the screen and the API agree.
    """
    src = (ROOT / "web" / "src" / "App.jsx").read_text()
    block = src[src.index("const ALL_TABS"):src.index("}\n\nexport default")]
    out = []
    for m in re.finditer(
            r'\["(/[^"]*)",\s*"([^"]+)",\s*"([^"]+)",\s*(?:"([^"]+)"|null)\]',
            block):
        out.append((m.group(1), m.group(2), m.group(3), m.group(4)))
    return out


#: What a screen actually calls when it opens, derived from the source
#: rather than restated here.
#:
#: This was a hand-kept map and it was wrong four times in one run — it sent
#: the probe at /api/timesheet/2025, /api/facilities/assets and
#: /api/documents/inbox, none of which any screen calls, and reported three
#: correct 404s and a correct 403 as faults. A review instrument that
#: invents its own idea of what a page does produces findings about itself.
#:
#: So: App.jsx says which component a path renders, the component says which
#: api.* helpers it calls, and api.js says what each of those fetches.
def _tab_endpoints() -> dict[str, str | None]:
    app = (ROOT / "web" / "src" / "App.jsx").read_text()
    api_js = (ROOT / "web" / "src" / "api.js").read_text()

    routes = dict(re.findall(
        r'<Route path="([^"]+)" element=\{<(\w+)', app))

    # helper name -> the path it requests, first one wins
    helpers: dict[str, str] = {}
    for m in re.finditer(r"^\s{2}(\w+):\s*(.*?)(?=\n  \w+:|\n\};)",
                         api_js, re.S | re.M):
        name, body = m.group(1), m.group(2)
        # Stop at ? or $ — a query string is not part of the path, and a
        # template placeholder would otherwise leak into it.
        u = re.search(r'req\(\s*[`"\']([^`"\'?$]+)', body)
        if u:
            helpers[name] = "/api" + u.group(1)

    out: dict[str, str | None] = {}
    for path, component in routes.items():
        page = ROOT / "web" / "src" / "pages" / f"{component}.jsx"
        if not page.exists():
            out[path] = None
            continue
        src = page.read_text()
        called = [helpers[n] for n in re.findall(r"api\.(\w+)\(", src)
                  if n in helpers]
        # The first helper a page calls on mount is the one that decides
        # whether the screen comes up at all.
        out[path] = called[0] if called else None
    return out


TAB_ENDPOINT = _tab_endpoints()


def _holds(me: dict, needs: str | None) -> bool:
    if not needs:
        return True
    if needs == "staff":
        return bool(me.get("employee_key"))
    if needs == "admin":
        return bool(me.get("is_admin"))
    if needs == "reader":
        return bool(me.get("can_read"))
    if me.get("role") == "AUDITOR":
        return True
    return needs in (me.get("portfolios") or [])


def capability(clients: dict[str, httpx.Client]) -> None:
    print("\nCAPABILITY — the nav against what the API will actually allow")
    tabs = _tabs()
    facts["tabs"] = [{"path": t[0], "label": t[1], "schedule": t[2],
                      "needs": t[3]} for t in tabs]
    matrix: dict[str, dict[str, str]] = defaultdict(dict)

    for name, c in clients.items():
        me = c.get("/api/auth/me").json()
        for path, label, _sched, needs in tabs:
            endpoint = TAB_ENDPOINT.get(path)
            shown = _holds(me, needs)
            if endpoint is None:
                matrix[label][name] = "shown" if shown else "hidden"
                continue
            r = c.get(endpoint)
            works = r.status_code < 400
            matrix[label][name] = (
                f"{'shown' if shown else 'hidden'}/{r.status_code}")
            if shown and not works:
                finding("CAPABILITY", FAULT,
                        f"{name} is shown the {label!r} tab and {endpoint} "
                        f"answers {r.status_code}",
                        "A tab that answers 403 reads as a system that does "
                        "not know who you are.",
                        "Either gate the tab on what the endpoint requires, "
                        "or widen the endpoint.")
            if not shown and works and r.status_code == 200:
                # Not automatically wrong — an endpoint can be legitimately
                # readable by somebody with no tab for it — but worth seeing.
                finding("CAPABILITY", NOTE,
                        f"{name} is not shown {label!r} but {endpoint} "
                        f"answers 200",
                        "Reachable by URL and absent from the nav.")
    facts["capability_matrix"] = dict(matrix)
    ok(f"{len(tabs)} tabs checked against their endpoint for "
       f"{len(clients)} people")


# ── 3. Functionality — do the screens carry anything ─────────────────

#: Screens that must carry data on a seeded system, and the count that says
#: so. A screen that is empty because nobody has done the work is a GAP; a
#: screen that is empty because it is broken is a FAULT, and the only way to
#: tell them apart is to say in advance what "working" looks like.
EXPECTED = [
    ("/api/classify/queue", "groups", 1, "the classification queue"),
    ("/api/reconcile", "controls", 11, "the eleven control points"),
    ("/api/documents/library", "documents", 18, "the document library"),
    ("/api/contracts", "contracts", 3, "the award register"),
    ("/api/reports/invoices", "invoices", 3, "the invoice register"),
    ("/api/chart/accounts", "accounts", 80, "the 2026 chart"),
    ("/api/contracts/employees", "employees", 40, "the payroll"),
    ("/api/certify/status", "people", 40, "certification status"),
]


def functionality(c: httpx.Client, admin: httpx.Client) -> None:
    print("\nFUNCTIONALITY — the screens that should carry data carry data")
    counts = {}
    # The roster belongs to whoever provisions, not to whoever classifies.
    # Probing it as the controller asserted the opposite of the access model
    # and reported a correct 403 as a fault.
    r = admin.get("/api/auth/actors")
    if r.status_code != 200:
        finding("FUNCTIONALITY", FAULT,
                f"the roster answers {r.status_code} to an administrator",
                "/api/auth/actors")
    elif len(r.json()) < 6:
        finding("FUNCTIONALITY", GAP,
                f"the roster carries {len(r.json())} accounts, expected 6")
    else:
        ok(f"the roster: {len(r.json())}")
    for path, key, least, what in EXPECTED:
        r = c.get(path)
        if r.status_code != 200:
            finding("FUNCTIONALITY", FAULT,
                    f"{what} answers {r.status_code}", path)
            continue
        body = r.json()
        rows = body if isinstance(body, list) else body.get(key) if key else body
        n = len(rows) if isinstance(rows, (list, dict)) else 0
        counts[path] = n
        if n < least:
            finding("FUNCTIONALITY", GAP,
                    f"{what} carries {n} rows, expected at least {least}",
                    path,
                    "Either the seed did not load or the view lost rows.")
        else:
            ok(f"{what}: {n}")
    facts["counts"] = counts


# ── 4. Auditability ──────────────────────────────────────────────────

def auditability(c: httpx.Client) -> None:
    """Every change names somebody, and the trail can be read back.

    The claim this system makes is not that it is correct — it is that you
    can tell who decided what and when. That claim is worth exactly what it
    is tested at.
    """
    print("\nAUDITABILITY — every change names somebody")
    from app.db import one, query

    total = one("SELECT count(*) AS n FROM audit_log")["n"]
    facts["audit_rows"] = total

    # The third copy of one predicate — `drive_state_machine` and
    # `drive_everyone` held the other two, and all three reported the
    # deployment bootstrap's honest rows as faults on a record built from
    # nothing. Defined once in `v_audit_orphan`; migration `087`.
    orphan = one("""SELECT count(*) AS n FROM v_audit_orphan""")["n"]
    if orphan:
        finding("AUDITABILITY", FAULT,
                f"{orphan} audit entries name no account or no session",
                "A change nobody can be asked about is not an audit trail.")
    else:
        ok(f"{total} audit entries, every one naming an account and a session")

    no_reason = one("""SELECT count(*) AS n FROM audit_log
                        WHERE coalesce(reason, '') = ''""")["n"]
    if no_reason:
        finding("AUDITABILITY", NOTE,
                f"{no_reason} of {total} entries carry no reason",
                "A reason is what makes an entry answerable rather than "
                "merely present.")

    # Every mutating route should be able to explain itself. The structural
    # test in pytest proves each one *calls* record(); this proves the rows
    # actually landed on a live system, which is a different claim.
    kinds = query("""SELECT action, count(*) AS n FROM audit_log
                      GROUP BY action ORDER BY count(*) DESC""")
    facts["audit_by_action"] = {r["action"]: r["n"] for r in kinds}
    ok(f"{len(kinds)} distinct actions on the record")

    actors = query("""SELECT actor, actor_role::text AS role, count(*) AS n
                        FROM audit_log GROUP BY actor, actor_role
                       ORDER BY count(*) DESC""")
    facts["audit_by_actor"] = [dict(a) for a in actors]
    silent = [w[1] for w in WHO
              if not any(w[0] in str(a["actor"]) or w[1] in str(a["actor"])
                         for a in actors)]
    if silent:
        finding("AUDITABILITY", NOTE,
                f"{', '.join(silent)} left no trace on the record",
                "Not a fault on a freshly seeded system — nobody has done "
                "anything yet — but it means their trail is untested here.")


# ── 5. Continuity — forward and backward ─────────────────────────────

def continuity(c: httpx.Client) -> None:
    """Walk the chain both ways.

    Forward is how the work is done. Backward is how it is *checked*, and it
    is the direction that finds broken links, because forward you only ever
    visit rows that exist.
    """
    print("\nCONTINUITY — the chain, forward and then backward")
    from app.db import one, query

    # Forward: ledger -> group -> classification -> pool -> rate -> invoice
    chain = [
        ("ledger lines", "SELECT count(*) AS n FROM ledger_line WHERE period='2025'"),
        ("groups still unclassified", "SELECT count(*) AS n FROM v_unclassified"),
        ("decisions recorded", "SELECT count(*) AS n FROM decision "
                               "WHERE reversed_at IS NULL"),
        ("sealed sets", "SELECT count(*) AS n FROM decision_set WHERE sealed_at IS NOT NULL"),
        ("rates", "SELECT count(*) AS n FROM rate WHERE status <> 'SUPERSEDED'"),
        ("allocations", "SELECT count(*) AS n FROM allocation"),
        ("invoices", "SELECT count(*) AS n FROM invoice"),
        ("restatements", "SELECT count(*) AS n FROM restatement"),
    ]
    forward = {}
    for label, sql in chain:
        try:
            forward[label] = one(sql)["n"]
        except Exception as exc:                       # noqa: BLE001
            finding("CONTINUITY", FAULT, f"cannot count {label}", str(exc)[:160])
            forward[label] = None
    facts["forward_chain"] = forward
    for label, n in forward.items():
        ok(f"{label}: {n}")

    # The forward chain stops where the work stops, and saying where is the
    # single most useful thing this review can report.
    seen = False
    stops = None
    for label, n in forward.items():
        if n:
            seen = True
        elif seen and stops is None:
            stops = label
    if stops:
        finding("CONTINUITY", GAP,
                f"the chain stops at {stops!r}",
                f"Everything upstream is loaded; nothing downstream of "
                f"{stops} exists yet.",
                "This is the work, not a defect. It is named here so a "
                "reviewer is not left to infer it from an empty screen.")

    # Backward: can every figure that exists be walked to the ledger?
    orphans = [
        ("live decisions belonging to no decision set",
         """SELECT count(*) AS n FROM decision d
             WHERE d.reversed_at IS NULL
               AND NOT EXISTS (SELECT 1 FROM decision_set s
                                WHERE s.set_id = d.set_id)"""),
        ("allocations pointing at no rate",
         """SELECT count(*) AS n FROM allocation a
             WHERE NOT EXISTS (SELECT 1 FROM rate r
                                WHERE r.rate_id = a.rate_id)"""),
        ("invoice lines with no invoice",
         """SELECT count(*) AS n FROM invoice_line l
             WHERE NOT EXISTS (SELECT 1 FROM invoice i
                                WHERE i.invoice_id = l.invoice_id)"""),
        ("attachments pointing at no document",
         """SELECT count(*) AS n FROM attachment t
             WHERE NOT EXISTS (SELECT 1 FROM evidence e
                                WHERE e.evidence_id = t.evidence_id)"""),
        ("evidence rows whose file is gone",
         None),
    ]
    for label, sql in orphans:
        if sql is None:
            continue
        try:
            n = one(sql)["n"]
        except Exception as exc:                       # noqa: BLE001
            finding("CONTINUITY", NOTE, f"could not check {label}",
                    str(exc)[:160])
            continue
        if n:
            finding("CONTINUITY", FAULT, f"{n} {label}",
                    "A row that points at nothing cannot be walked back to "
                    "the ledger, which is the only thing that makes it "
                    "evidence.")
        else:
            ok(f"no {label}")

    # The index and the volume must agree. The database is the index; a row
    # whose file is missing is the two having parted company.
    from pathlib import Path as _P
    missing = [r["evidence_id"] for r in query("SELECT evidence_id, uri FROM evidence")
               if not _P(r["uri"]).exists()]
    if missing:
        finding("CONTINUITY", FAULT,
                f"{len(missing)} documents are indexed but not on the volume",
                ", ".join(missing[:6]),
                "The database is the index and the tree is for people; when "
                "they disagree the index is what a reader trusts and it is "
                "wrong.")
    else:
        ok("every indexed document is on the volume")


# ── 5b. The backward walk, through the API rather than the schema ────

def backward(clients: dict[str, httpx.Client]) -> None:
    """Start at a figure a reviewer is handed and walk to the ledger.

    The orphan checks above read the schema. This reads what an *auditor*
    can actually get to from a screen, which is a different question: a
    foreign key can be intact while the route that would let somebody follow
    it does not exist, and then the chain is unbroken and unwalkable.
    """
    print("\nCONTINUITY (backward) — from a figure to the ledger, by API")
    a = clients["Auditor"]

    steps: list[tuple[str, str]] = []

    def step(what: str, r) -> bool:
        good = r.status_code == 200
        steps.append((what, "ok" if good else str(r.status_code)))
        (ok if good else lambda m: finding("CONTINUITY", FAULT, m,
                                           "the backward walk stops here"))(
            f"{what} — {r.status_code}")
        return good

    # An invoice is where an auditor starts, because it is the thing the
    # sponsor paid against.
    r = a.get("/api/reports/invoices")
    if not step("the invoice register", r):
        return
    invoices = r.json().get("invoices", [])
    if not invoices:
        finding("CONTINUITY", GAP, "no invoices to walk back from")
        return
    inv = invoices[0]

    step(f"invoice {inv['invoice_number']} as a document",
         a.get(f"/api/reports/invoice/{inv['invoice_number']}"))

    objective = inv.get("objective_id")
    if objective:
        step(f"the objective {objective} it was billed against",
             a.get(f"/api/contracts/charge-codes/{objective}/people"))

    award = inv.get("award_id")
    if award:
        # One request, not four. The detail route carries the terms, the
        # milestones, the invoices and the people together, because a
        # drill-down that needs four round trips is one somebody abandons
        # halfway. Probing /terms and /milestones as GETs was this review
        # inventing routes again — they are PUT and POST, for recording.
        r = a.get(f"/api/contracts/{award}")
        if step(f"the award {award} behind it", r):
            detail = r.json()
            terms = detail.get("terms") or []
            if not terms:
                finding("CONTINUITY", GAP,
                        f"{award} carries no provisions",
                        "An auditor reaches the agreement and finds nothing "
                        "in it. The ceiling, the term and the indirect "
                        "provision are all clauses somebody has to have read.",
                        "scripts/load_contract_terms.py records them.")
            else:
                uncited = [t["term_key"] for t in terms
                           if not (t.get("citation") or "").strip()]
                if uncited:
                    finding("CONTINUITY", GAP,
                            f"{len(uncited)} provision(s) on {award} name no "
                            f"clause", ", ".join(uncited),
                            "A provision with no citation is somebody's "
                            "recollection of a contract.")
                else:
                    ok(f"{len(terms)} provisions, every one naming its clause")
            steps.append((f"{award} provisions", f"{len(terms)}"))
    else:
        finding("CONTINUITY", GAP,
                f"invoice {inv['invoice_number']} names no award",
                "It can be walked to an objective but not to the agreement "
                "that authorised it.",
                "Set award_id on the invoice, or record why it has none.")

    # And from the people to the cost: who charged, and what the ledger says.
    r = a.get("/api/contracts/employees")
    if step("everybody who charged time", r):
        people = r.json().get("employees", [])
        if people:
            key = people[0]["employee_key"]
            step(f"what {key} charged, and to what",
                 a.get(f"/api/contracts/employees/{key}/charging"))
            step(f"{key}'s effort distribution",
                 a.get(f"/api/certify/{key}"))

    # The document behind a figure.
    r = a.get("/api/documents/library?limit=1")
    if step("the document library", r):
        docs = r.json().get("documents", [])
        if docs:
            step("and a document opened from it",
                 a.get(f"/api/documents/{docs[0]['evidence_id']}/file"))

    facts["backward_walk"] = steps
    ok(f"{sum(1 for _, v in steps if v == 'ok')}/{len(steps)} links walkable "
       f"by an auditor with no portfolio")


# ── 6. Proportion — a change moves what it should, and no more ───────

def proportion(clients: dict[str, httpx.Client]) -> None:
    """Change one thing and measure everything.

    The dimension nothing else covers. A system can pass every boundary
    check and still let one edit move a figure three screens away that
    nobody connected to it — or fail to move one that should have moved.
    Both are how a reconciliation stops meaning anything.
    """
    print("\nPROPORTION — a change moves what it should, by what it should")
    from app.db import one

    tom = clients["Tom"]

    def snapshot() -> dict:
        return {
            "classified_dollars": one(
                "SELECT coalesce(pct_dollars_covered, 0) AS v "
                "FROM v_classification_coverage WHERE period = '2025'")["v"],
            "decisions": one("SELECT count(*) AS n FROM decision "
                             "WHERE reversed_at IS NULL")["n"],
            "audit": one("SELECT count(*) AS n FROM audit_log")["n"],
            "ledger": one("SELECT coalesce(sum(amount),0) AS v "
                          "FROM ledger_line WHERE period='2025'")["v"],
            "register": one("SELECT register_wages AS v "
                            "FROM v_payroll_reconciliation "
                            "WHERE period='2025'")["v"],
            "open_controls": one(
                "SELECT count(*) AS n FROM v_statement_reconciliation "
                "WHERE state <> 'TIES'")["n"],
        }

    before = snapshot()
    facts["proportion_before"] = {k: str(v) for k, v in before.items()}

    # Find a group to classify, and classify it. One decision, and then
    # everything else is measured.
    q = tom.get("/api/classify/queue?limit=1")
    groups = q.json() if q.status_code == 200 else []
    if not isinstance(groups, list) or not groups:
        finding("PROPORTION", NOTE, "no group available to test a change with",
                "The queue is empty, so the propagation of a classification "
                "could not be measured.")
        return
    group = groups[0]
    facts["proportion_group"] = {"account": group["account"],
                                 "amount": str(group["amount"]),
                                 "lines": group["line_count"]}

    body = {"group_keys": [group["group_key"]],
            "pool": "G&A", "function_990": "MANAGEMENT_AND_GENERAL", "federal": "PENDING",
            "grade": "CORROBORATED",
            "rationale": "System review: one decision, recorded so the review "
                         "can measure what it moves and what it must not."}
    r = tom.post("/api/classify/decide", json=body)
    if r.status_code >= 400:
        # A sealed set refusing a new classification is the guarantee the
        # whole engagement rests on, not a fault. Reading it as one is what
        # this check did on its first run after the drives, which seal.
        sealed = ("sealed" in r.text.lower()
                  or "no open decision set" in r.text.lower())
        if sealed:
            ok("a sealed decision set refuses a new classification — "
               "the seal holds")
            finding("PROPORTION", NOTE,
                    "propagation was not measured in this run",
                    "The decision set is sealed, so no change could be made "
                    "to measure. That is the correct state, not a defect.",
                    "Run the review on a freshly seeded database, before the "
                    "drives — they seal. ./scripts/seed.sh then this.")
        else:
            finding("PROPORTION", FAULT,
                    f"a controller could not record a classification "
                    f"({r.status_code})", r.text[:200])
        return

    after = snapshot()
    facts["proportion_after"] = {k: str(v) for k, v in after.items()}

    moved = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    held = [k for k in before if before[k] == after[k]]
    facts["proportion_moved"] = {k: [str(a), str(b)] for k, (a, b) in moved.items()}

    # What must move
    added = after["decisions"] - before["decisions"]
    if added < 1:
        finding("PROPORTION", FAULT,
                "a classification was accepted and no live decision appeared",
                f"{before['decisions']} -> {after['decisions']}")
    else:
        # A group is an account and a payee; the decision is recorded per
        # line, because that is what the evidence gate reads and what keeps
        # a document tied to the dollars it supports when a group is split.
        ok(f"classifying one group of {group['line_count']} lines added "
           f"{added} live decision(s)")
        if added != group["line_count"]:
            finding("PROPORTION", NOTE,
                    f"the group carries {group['line_count']} lines and "
                    f"{added} decision(s) were recorded",
                    "Not necessarily wrong — scope may be the group rather "
                    "than the line — but worth knowing which.")

    if after["audit"] <= before["audit"]:
        finding("PROPORTION", FAULT,
                "a classification was recorded and the audit log did not grow",
                f"{before['audit']} -> {after['audit']}")
    else:
        ok(f"and {after['audit'] - before['audit']} audit entr(y|ies) with it")

    # What must NOT move. A classification is a judgment about cost already
    # in the ledger; if it changes the ledger, the ledger is not the source.
    for key, why in (
            ("ledger", "classifying cost must not change the cost"),
            ("register", "classifying cost must not touch the payroll register"),
            ("open_controls", "classifying cost must not open or close a "
                              "cross-reference control")):
        if before[key] != after[key]:
            finding("PROPORTION", FAULT, f"{why}",
                    f"{key}: {before[key]} -> {after[key]}")
        else:
            ok(f"{why} — held")

    if before["classified_dollars"] is not None:
        if after["classified_dollars"] == before["classified_dollars"]:
            finding("PROPORTION", NOTE,
                    "coverage did not move on one classification",
                    f"{before['classified_dollars']}% before and after — "
                    f"possible on a rounded percentage over 999 groups.")
        else:
            ok(f"coverage moved {before['classified_dollars']}% -> "
               f"{after['classified_dollars']}%")

    # Put it back. A review that leaves its own test data behind changes
    # the thing it is measuring, and the next run measures the run before
    # it — coverage climbed 0% to 36.8% over five runs before this existed,
    # and every one of those figures was a review reading its own writing.
    #
    # Through the real undo route, which is itself worth exercising: a
    # system that cannot walk its own changes back has a guarantee it has
    # never tested.
    back = tom.post("/api/undo", json={
        "count": 1,
        "reason": "System review: reversing the single decision this review "
                  "made, so the review leaves the record as it found it."})
    if back.status_code >= 400:
        finding("PROPORTION", FAULT,
                f"the review could not walk back its own change "
                f"({back.status_code})", back.text[:200],
                "Every run of this review will leave a decision behind and "
                "the baseline will drift.")
    else:
        restored = snapshot()
        if restored["decisions"] == before["decisions"]:
            ok("and the review walks its own change back, leaving the record "
               "as it found it")
        else:
            finding("PROPORTION", FAULT,
                    "undo did not restore the decision count",
                    f"{before['decisions']} before, {after['decisions']} "
                    f"after the change, {restored['decisions']} after undo")

    # And the seal: no rate may exist while classification is open, however
    # much of it is done. This is the guarantee the whole system rests on.
    r = tom.post("/api/rates/compute", params={"period": "2025"}, json={})
    if r.status_code == 200:
        finding("PROPORTION", FAULT,
                "a rate was computed over an unsealed decision set",
                "This is the guarantee the engagement rests on.",
                "rate_requires_seal should have refused this.")
    else:
        ok(f"a rate over an unsealed set is refused — {r.status_code}")


def _has_view(name: str) -> bool:
    from app.db import one
    return bool(one("SELECT 1 AS x FROM information_schema.views "
                    "WHERE table_name = %s", (name,)))


# ── The report ───────────────────────────────────────────────────────

def write_report(out: Path, base: str) -> None:
    by_dim: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        by_dim[f["dimension"]].append(f)
    counts = {s: sum(1 for f in findings if f["severity"] == s)
              for s in (FAULT, GAP, NOTE)}

    lines = [
        "# System review",
        "",
        f"Generated by `scripts/review_system.py` against a database seeded "
        f"from nothing, {datetime.now(timezone.utc):%Y-%m-%d}.",
        "",
        "Six dimensions, because a system can be sound on one and broken on "
        "another and the failure modes do not look alike. A **FAULT** is the "
        "system not working. A **gap** is it working over data nobody has "
        "supplied yet — a different conversation, and reporting the two as "
        "the same thing is how a review stops being read.",
        "",
        f"| | |", "| --- | --- |",
        f"| Faults | {counts[FAULT]} |",
        f"| Gaps | {counts[GAP]} |",
        f"| Notes | {counts[NOTE]} |",
        f"| GET routes probed | {facts.get('routes_probed')} "
        f"(× {len(WHO)} people) |",
        f"| Audit entries | {facts.get('audit_rows')} |",
        "",
    ]

    lines += ["## Who was driven", ""]
    for email, name, role, what in WHO:
        lines.append(f"- **{name}** — `{role}`. {what}")
    lines.append("")

    for dim in ("CONNECTIVITY", "CAPABILITY", "FUNCTIONALITY",
                "AUDITABILITY", "CONTINUITY", "PROPORTION"):
        lines += [f"## {dim.title()}", ""]
        rows = by_dim.get(dim, [])
        if not rows:
            lines += ["Nothing found.", ""]
            continue
        for f in rows:
            lines.append(f"### {f['severity']} — {f['what']}")
            if f["detail"]:
                lines.append("")
                lines.append(f["detail"])
            if f["fix"]:
                lines.append("")
                lines.append(f"*What to do:* {f['fix']}")
            lines.append("")

    lines += ["## What the system held at the moment of review", "",
              "```json",
              json.dumps({k: v for k, v in facts.items()
                          if k not in ("route_matrix", "capability_matrix")},
                         indent=2, default=str),
              "```", ""]

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    print(f"\nwritten to {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default="docs/SYSTEM_REVIEW.md")
    args = ap.parse_args()

    password = os.environ.get("YBI_SEED_PASSWORD", "")
    if not password:
        raise SystemExit("YBI_SEED_PASSWORD is required to drive the review.")

    try:
        health = httpx.get(f"{args.base}/api/health", timeout=30)
    except httpx.HTTPError as exc:
        raise SystemExit(f"nothing serving at {args.base}: {exc}") from exc
    if health.status_code != 200:
        raise SystemExit(f"{args.base} answered {health.status_code}")

    clients: dict[str, httpx.Client] = {}
    for email, name, role, _ in WHO:
        c = sign_in(args.base, email, password)
        if c is None:
            raise SystemExit(
                f"could not sign in as {email}. The review is worthless "
                f"without every actor — a signed-out client and a correctly "
                f"refusing server look identical.")
        clients[name] = c

    from app.db import open_pool
    open_pool()

    try:
        connectivity(args.base, clients)
        capability(clients)
        functionality(clients["Tom"], clients["Barb"])
        auditability(clients["Tom"])
        continuity(clients["Tom"])
        backward(clients)
        proportion(clients)
    finally:
        for c in clients.values():
            c.close()

    write_report(Path(args.out), args.base)

    faults = sum(1 for f in findings if f["severity"] == FAULT)
    gaps = sum(1 for f in findings if f["severity"] == GAP)
    print(f"\n{faults} fault(s), {gaps} gap(s), "
          f"{len(findings) - faults - gaps} note(s)")
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
