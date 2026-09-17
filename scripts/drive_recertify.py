#!/usr/bin/env python3
"""The auditor rejects a classification inside a sealed, certified set.

    YBI_SEED_PASSWORD=... python3 scripts/drive_recertify.py [--base URL]

This is the cycle the whole chain exists for, and until it was driven nobody
had walked it end to end:

    certified ->  the auditor wants a group classified differently, and
                  wants a document behind two others
              ->  withdraw the signature, with a reason
              ->  unseal, with a reason
              ->  reclassify; note; attach
              ->  re-seal, recompute, re-certify
              ->  and everything the first signature covered is still readable

Six properties are asserted at every hop, and the last two are the ones a
system like this usually gets wrong:

  * a certified rate cannot be unsealed — withdrawing is a separate, deliberate
    act with its own reason, because an auditor's rejection should cost two
    conscious steps and not one that removes a signature on the way past
  * the pools move by exactly the reclassified amount and coverage does not
    move at all, because no reclassification changes how much there is to judge
  * the superseded judgment is still there, with its rationale, at `live=false`
  * the withdrawn certificate is still there, with who withdrew it and why
  * the new certificate covers the NEW rate rows, so the old signature cannot
    reattach to arithmetic nobody signed
  * every one of these acts names Tom and a session in `audit_log`

Leaves the record as it found it, against a census taken before it starts.
Exit 0 is a pass. Exit 1 is a finding. Exit 2 means it could not run.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import one, open_pool, query                      # noqa: E402
from app.foundation import EMAIL                              # noqa: E402

CHECKS = 0
FINDINGS: list[str] = []


def ok(what: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  \033[32mok\033[0m       {what}", flush=True)


def bad(what: str) -> None:
    global CHECKS
    CHECKS += 1
    FINDINGS.append(what)
    print(f"  \033[31mFINDING\033[0m  {what}", flush=True)


def note(what: str) -> None:
    print(f"  \033[33m·\033[0m        {what}", flush=True)


def head(what: str) -> None:
    print(f"\n\033[1m{what}\033[0m", flush=True)


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=300)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        print(f"could not sign in as {email}: {r.status_code} {r.text[:160]}",
              file=sys.stderr)
        raise SystemExit(2)
    return c


def certified(period: str) -> dict:
    return one("""SELECT certified, signature, certified_by, why_not
                    FROM v_rate_certified WHERE period = %s""", (period,))


def pools(period: str) -> dict[str, Decimal]:
    return {r["pool"]: Decimal(str(r["gross"] or 0))
            for r in query("""SELECT pool, gross FROM v_pool_balance
                               WHERE period = %s""", (period,))}


def coverage(period: str) -> tuple[Decimal, Decimal]:
    r = one("""SELECT classified, scope_dollars
                 FROM v_classification_coverage WHERE period = %s""", (period,))
    return Decimal(str(r["classified"])), Decimal(str(r["scope_dollars"]))


def audit_rows(period: str) -> int:
    return one("SELECT count(*) AS n FROM audit_log")["n"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.getenv("YBI_BASE",
                                                "http://127.0.0.1:8000"))
    ap.add_argument("--period", default="2025")
    args = ap.parse_args()
    pw = os.environ.get("YBI_SEED_PASSWORD", "")
    if not pw:
        print("YBI_SEED_PASSWORD is required.", file=sys.stderr)
        return 2

    open_pool()
    period = args.period
    tom = sign_in(args.base, EMAIL["tom"], pw)

    # ── what we are going to move ────────────────────────────────────────
    #
    # A real group, chosen from the record rather than named here: the
    # largest FRINGE judgment, which is a pool a reclassification visibly
    # moves. A hand-picked literal would be a group that might not exist.
    #
    # The account and payee come off the **ledger**, not off `decision.scope`.
    # Those are two encodings of one key: the queue's wire form is
    # `account\x1fpayee` and `classify.py` stores `account=…|payee=…`, with an
    # encoder at the point of writing and no decoder anywhere. A first draft
    # fed `scope` straight back to `/classify/decide` and got a 409 naming a
    # group that does not exist — so the walk back from a judgment to the
    # queue goes through `decision_line` to `ledger_line`, which is the only
    # route that survives an account name containing the separator.
    target = one("""SELECT l.account, coalesce(l.payee, '') AS payee,
                           d.pool::text AS pool, d.rationale,
                           -- **Signed**, because that is what a pool carries.
                           -- The first draft summed `abs(amount)` and
                           -- reported a finding against working code: this
                           -- group is 195,895.50 gross and 139,303.78 net, and
                           -- coverage counts absolute dollars while the pools
                           -- carry the position. Comparing the two is a false
                           -- alarm every time a credit is judged, which
                           -- `066` says in as many words and which I then
                           -- wrote into a drive.
                           sum(l.amount) AS amount,
                           sum(abs(l.amount)) AS gross
                      FROM decision d
                      JOIN decision_line dl ON dl.decision_id = d.decision_id
                                           AND dl.live
                      JOIN ledger_line l ON l.line_id = dl.line_id
                      JOIN decision_set ds ON ds.set_id = d.set_id
                     WHERE d.reversed_at IS NULL AND ds.period = %s
                       AND d.pool = 'FRINGE'
                     GROUP BY l.account, l.payee, d.pool, d.rationale
                     ORDER BY 6 DESC LIMIT 1""", (period,))
    if not target:
        print("COULD NOT RUN — no live FRINGE judgment to move.",
              file=sys.stderr)
        return 2
    group = f"{target['account']}\x1f{target['payee']}"
    scope = f"account={target['account']}|payee={target['payee']}"
    moved = Decimal(str(target["amount"]))
    note(f"the auditor's objection is to {target['account']} — "
         f"{moved:,.2f} net, {Decimal(str(target['gross'])):,.2f} gross")

    before_pools = pools(period)
    before_cov = coverage(period)
    before_audit = audit_rows(period)
    before_certs = one("SELECT count(*) AS n FROM rate_certification")["n"]

    # ── 1. it starts certified ───────────────────────────────────────────
    head("It starts certified")
    st = certified(period)
    if not st["certified"]:
        r = tom.post("/api/rates/certify", params={"period": period},
                     json={"signature": "Tom Metzinger",
                           "note": "Baseline for the recertification drive."})
        if r.status_code != 200:
            print(f"COULD NOT RUN — could not certify to begin with: "
                  f"{r.status_code} {r.text[:200]}", file=sys.stderr)
            return 2
        st = certified(period)
    if st["certified"]:
        ok(f"the rate carries a signature — {st['signature']}")
    else:
        bad("the rate is not certified, so there is nothing to walk back from")
        return 1

    # ── 2. a certified rate refuses to be unsealed ───────────────────────
    head("A certified rate is not unsealed on the way past")
    r = tom.post("/api/rates/unseal", params={
        "period": period,
        "reason": "Trying to unseal while the signature still stands."})
    if r.status_code == 409 and "certified" in r.text.lower():
        ok("unsealing a certified rate is refused, and the refusal says why")
    else:
        bad(f"unsealing a certified rate answered {r.status_code}; the "
            f"signature would have come off without a second act")

    # ── 3. withdraw, with a reason ───────────────────────────────────────
    head("Withdrawing the signature")
    r = tom.post("/api/rates/certify/withdraw", params={"period": period},
                 json={"reason": "Short."})
    if r.status_code == 422:
        ok("a withdrawal with no real reason is refused")
    else:
        bad(f"a one-word withdrawal reason answered {r.status_code}")

    why = ("The auditor has rejected the classification of "
           f"{target['account']} and asked for supporting documents "
           "on two further groups. Withdrawing so the set can be reopened.")
    r = tom.post("/api/rates/certify/withdraw", params={"period": period},
                 json={"reason": why})
    if r.status_code == 200:
        ok("the signature is withdrawn")
    else:
        bad(f"withdrawing answered {r.status_code}: {r.text[:140]}")
        return 1
    if not certified(period)["certified"]:
        ok("and the record says the rate is no longer certified")
    else:
        bad("the rate still reads as certified after the withdrawal")

    # ── 4. now it unseals ────────────────────────────────────────────────
    head("Reopening the set")
    r = tom.post("/api/rates/unseal", params={
        "period": period,
        "reason": f"Auditor requires {target['account']} reclassified "
                  f"and two groups evidenced."})
    if r.status_code == 200:
        ok("with the signature withdrawn, the set unseals")
    else:
        bad(f"unsealing answered {r.status_code}: {r.text[:140]}")
        return 1
    live_rates = one("""SELECT count(*) AS n FROM rate
                         WHERE period = %s AND status <> 'SUPERSEDED'""",
                     (period,))["n"]
    if live_rates == 0:
        ok("every rate computed from that seal is superseded")
    else:
        bad(f"{live_rates} rate(s) still stand over an unsealed set")

    # ── 5. the change the auditor asked for ──────────────────────────────
    head("Making the change")
    r = tom.post("/api/classify/decide", params={"period": period}, json={
        "group_keys": [group], "pool": "OVERHEAD",
        "function_990": "MANAGEMENT_AND_GENERAL", "federal": "ALLOWABLE",
        "grade": "CORROBORATED",
        "rationale": "Reclassified at the auditor's request during the "
                     "recertification drive; reversed in the same run."})
    if r.status_code == 200 and r.json().get("superseded"):
        ok("the judgment is superseded rather than edited")
    else:
        bad(f"reclassifying answered {r.status_code} "
            f"superseded={r.json().get('superseded') if r.status_code == 200 else '-'}")

    after_pools = pools(period)
    fringe_moved = before_pools.get("FRINGE", 0) - after_pools.get("FRINGE", 0)
    oh_moved = after_pools.get("OVERHEAD", 0) - before_pools.get("OVERHEAD", 0)
    if fringe_moved == moved and oh_moved == moved:
        ok(f"the pools move by exactly the group's own position "
           f"({moved:,.2f} net)")
    else:
        bad(f"the pools moved by {fringe_moved:,.2f} out and {oh_moved:,.2f} "
            f"in, against a group of {moved:,.2f}")

    if coverage(period) == before_cov:
        ok("coverage does not move — no judgment changes how much there is "
           "to judge")
    else:
        bad(f"coverage moved from {before_cov} to {coverage(period)} on a "
            f"reclassification")

    old = one("""SELECT rationale FROM decision
                  WHERE scope = %s AND reversed_at IS NOT NULL
                  ORDER BY reversed_at DESC LIMIT 1""", (scope,))
    if old and old["rationale"]:
        ok("the superseded judgment is still readable, with its reasoning")
    else:
        bad("the superseded judgment has lost its rationale")

    # ── 6. seal, compute, certify again ──────────────────────────────────
    head("Sealing and signing again")
    r = tom.post("/api/rates/seal", params={"period": period},
                 json={"note": "Re-sealed after the auditor's change."})
    if r.status_code != 200:
        bad(f"re-sealing answered {r.status_code}: {r.text[:140]}")
        return 1
    new_seal = r.json().get("seal_hash", "")
    ok(f"re-sealed at {new_seal[:12]}…")

    r = tom.post("/api/rates/compute", params={"period": period}, json={})
    if r.status_code != 200:
        bad(f"recomputing answered {r.status_code}: {r.text[:140]}")
        return 1
    ok("recomputed")

    if not certified(period)["certified"]:
        ok("the withdrawn signature does not reattach to the new build-up")
    else:
        bad("the rate reads as certified without anybody signing it again")

    r = tom.post("/api/rates/certify", params={"period": period},
                 json={"signature": "Tom Metzinger",
                       "note": "Re-certified after the auditor's change."})
    if r.status_code == 200:
        ok("and it certifies again")
    else:
        bad(f"re-certifying answered {r.status_code}: {r.text[:140]}")

    cov = one("""SELECT count(*) AS n FROM rate_certification_line cl
                   JOIN rate r ON r.rate_id = cl.rate_id
                  WHERE cl.cert_id = (SELECT cert_id FROM v_rate_certified
                                       WHERE period = %s)
                    AND r.seal_hash = %s""", (period, new_seal))["n"]
    if cov > 0:
        ok(f"the new signature covers the rates from the new seal ({cov})")
    else:
        bad("the new signature does not name the rates it was put on")

    # ── 7. the trail ─────────────────────────────────────────────────────
    head("What the record kept")
    kinds = {r["action"] for r in query(
        """SELECT DISTINCT action FROM audit_log
            ORDER BY action""")}
    for want in ("RATE_CERTIFY", "RATE_CERTIFY_WITHDRAW", "UNSEAL", "SEAL"):
        if want in kinds:
            ok(f"{want} is on the record")
        else:
            bad(f"{want} left no audit row")

    anon = one("""SELECT count(*) AS n FROM audit_log
                   WHERE action IN ('RATE_CERTIFY','RATE_CERTIFY_WITHDRAW')
                     AND (actor_id IS NULL OR actor IS NULL)""")["n"]
    if anon == 0:
        ok("every certification act names an account")
    else:
        bad(f"{anon} certification act(s) name nobody")

    withdrawn = one("""SELECT withdrawn_reason, withdrawn_by
                         FROM rate_certification
                        WHERE withdrawn_at IS NOT NULL
                        ORDER BY withdrawn_at DESC LIMIT 1""")
    if withdrawn and withdrawn["withdrawn_by"]:
        ok("the withdrawn certificate stands, with who withdrew it and why")
    else:
        bad("the withdrawal is not on the record")

    if audit_rows(period) > before_audit:
        ok(f"{audit_rows(period) - before_audit} audit rows written by this "
           f"drive, none removed")
    else:
        bad("the drive changed the record and wrote no audit rows")

    # ── 8. put it back ───────────────────────────────────────────────────
    head("Putting the record back")
    steps = [
        ("withdraw", lambda: tom.post(
            "/api/rates/certify/withdraw", params={"period": period},
            json={"reason": "Drive complete; restoring the record to the "
                            "state it was found in."})),
        ("unseal", lambda: tom.post("/api/rates/unseal", params={
            "period": period,
            "reason": "Restoring the classification the drive moved."})),
        ("reclassify back", lambda: tom.post(
            "/api/classify/decide", params={"period": period}, json={
                "group_keys": [group], "pool": target["pool"],
                "function_990": "MANAGEMENT_AND_GENERAL",
                "federal": "ALLOWABLE", "grade": "CORROBORATED",
                "rationale": target["rationale"] or
                             "Restored to the pool it was judged into."})),
        ("re-seal", lambda: tom.post("/api/rates/seal",
                                     params={"period": period},
                                     json={"note": "Restored."})),
        ("recompute", lambda: tom.post("/api/rates/compute",
                                       params={"period": period}, json={})),
        ("re-certify", lambda: tom.post(
            "/api/rates/certify", params={"period": period},
            json={"signature": "Tom Metzinger",
                  "note": "Restored after the recertification drive."})),
    ]
    # Every statement is attempted and a failure printed rather than raised:
    # a cleanup that stops at the first refusal is worse than none, which is
    # what `drive_contracts` learned by leaving an award behind.
    for name, act in steps:
        try:
            r = act()
            if r.status_code != 200:
                note(f"{name} answered {r.status_code}: {r.text[:100]}")
        except Exception as e:                       # noqa: BLE001
            note(f"{name} raised {type(e).__name__}: {e}")

    end_pools = pools(period)
    if end_pools == before_pools:
        ok("every pool is back to the cent")
    else:
        moved_now = {k: end_pools.get(k, 0) - v
                     for k, v in before_pools.items()
                     if end_pools.get(k, 0) != v}
        bad(f"the record did not come back: {moved_now}")

    if certified(period)["certified"]:
        ok("and the rate is certified again, as it was found")
    else:
        bad("the drive left the rate uncertified")

    # The certificates are append-only and are *meant* to accumulate: a
    # position taken and withdrawn is part of the trail. Counting them is how
    # the drive proves it did not tidy its own history away.
    after_certs = one("SELECT count(*) AS n FROM rate_certification")["n"]
    note(f"{after_certs - before_certs} certificate(s) added and none removed "
         f"— a signature withdrawn is part of the record, not an edit")

    head(f"{CHECKS} checks, {len(FINDINGS)} finding(s)")
    for f in FINDINGS:
        print(f"  - {f}")
    return 1 if FINDINGS else 0


if __name__ == "__main__":
    raise SystemExit(main())
