"""One person, one active account — and the retired one keeps its history.

The roster carried `tom@ybi.org`, which was the naming convention rather than
a lookup. `077`'s bootstrap will not touch an account that exists, so it
correctly opened the real address, `tmetzinger@ybi.org`, *beside* the wrong
one and left two active accounts for one person. He has signed in as
`tmetzinger@`; `079` retires the other.

Two rules, and the second is the one that would cost the most:

  * **Retired, never removed.** 891 audit rows and all eighteen foundational
    documents point at that actor row — it is the provenance of the whole 2025
    classification. Deleting it orphans the record it authorised, which is
    what `POST /api/actors/{id}/active` says in its own docstring and what
    `027` chose when it corrected addresses in place.

  * **It fires only where the replacement is there to sign in as.** A recovery
    that restored the old row and not the new one would otherwise leave the
    controller with no account at all. A migration that can lock somebody out
    is worse than the duplicate it tidies.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "app" / "sql" / "079_one_tom.sql"


def test_the_migration_retires_and_never_removes():
    """No DELETE anywhere near the actor, and no rewriting of the trail."""
    body = re.sub(r"--[^\n]*", "", MIGRATION.read_text())

    assert "is_active = false" in body, (
        "079 no longer deactivates the superseded address")
    for forbidden in ("DELETE FROM actor", "DELETE FROM audit_log",
                      "DROP", "TRUNCATE"):
        assert forbidden.lower() not in body.lower(), (
            f"079 contains `{forbidden}` — the retired account authorised the "
            f"2025 classification and 891 audit rows point at it. Deleting it "
            f"orphans the record it authorised.")

    # The trail stays where it is. Repointing audit rows at the new account
    # would be inventing a history: those acts *were* performed on that one.
    assert "UPDATE audit_log" not in body, (
        "079 rewrites audit rows to point at the new account. Those acts were "
        "performed on the old one; moving them is inventing a history.")


def test_it_cannot_lock_the_controller_out():
    """The replacement has to exist and be active before the old one goes."""
    body = re.sub(r"--[^\n]*", "", MIGRATION.read_text())

    assert "tmetzinger@ybi.org" in body and "is_active" in body, (
        "079 no longer checks for the replacement account")
    # The retiring UPDATE must depend on the replacement row, not stand alone.
    retire = body[body.index("UPDATE actor"):body.index("RETURNING")]
    assert "replacement" in retire or "FROM" in retire, (
        "079 deactivates tom@ybi.org unconditionally. On a recovery that "
        "restored the old row and not the new one, the controller would have "
        "no account at all.")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_the_record_carries_one_active_tom_and_keeps_the_other_s_trail():
    from app.db import query

    rows = query("""SELECT email, is_active, actor_id FROM actor
                     WHERE display_name = 'Tom Metzinger' ORDER BY email""")
    if not rows:
        pytest.skip("no Tom on this record")

    active = [r for r in rows if r["is_active"]]
    assert len(active) == 1, (
        "one person, two ways in: " +
        ", ".join(f"{r['email']} active={r['is_active']}" for r in rows))
    assert active[0]["email"] == "tmetzinger@ybi.org", (
        f"the live account is {active[0]['email']}; he signs in as "
        f"tmetzinger@ybi.org")

    for r in rows:
        if r["is_active"]:
            continue
        n = query("SELECT count(*) AS n FROM audit_log WHERE actor_id = %s",
                  (r["actor_id"],))[0]["n"]
        assert n > 0, (
            f"{r['email']} was retired and its audit trail is gone. It "
            f"authorised the 2025 classification; the rows have to stand.")

# There is deliberately no test here that two live accounts cannot share an
# `employee_key`. Written, it passed — and then would not fail when the
# duplicate was forced, because `actor_employee_key` is a unique constraint and
# Postgres refuses the row outright. The invariant is in the schema, which is
# where this repository says it belongs; a test asserting it from outside would
# be one that cannot fail for the thing it names.

def test_no_script_signs_in_at_an_address_the_roster_no_longer_holds():
    """Fifty-two copies of `tom@ybi.org` across twenty-seven scripts.

    Every drive, the classification log and the request issuer carried it as a
    literal. When `079` retired that address all of them would have exited on a
    401 against a system working perfectly — and `prove.sh` runs nine of them,
    so the proof harness would have gone red for a reason that is not a defect,
    which is how a reader learns to ignore it.

    The rule is not *never write an address*: a drive that creates
    `peer-test@ybi.org` to prove the provisioning ladder is naming an account
    that is deliberately not on the roster, and several scripts check the
    `@ybi.org` suffix itself. The rule is that an address **for a person the
    roster knows** has to be the one the roster holds, because that is the copy
    that goes stale — and it did.

    `foundation.EMAIL` is derived from `ROSTER`, which is the one list of who
    these people are.
    """
    import ast
    import sys

    sys.path.insert(0, str(ROOT))
    from app.foundation import ROSTER

    live = {p.email for p in ROSTER}
    # First names *and* surnames. A first draft took surnames only and did not
    # fail when `tom@ybi.org` was pasted back into a drive — `tom` is a first
    # name, so the one address this test exists for was the one it could not
    # see. A test that cannot fail for the thing it names.
    known = set()
    for person in ROSTER:
        parts = person.display_name.lower().split()
        known.update(parts)
        known.add(person.email.split("@")[0].lower())

    offenders = []
    for f in sorted((ROOT / "scripts").glob("*.py")):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and node.value.endswith("@ybi.org")):
                continue
            addr = node.value
            if addr in live or addr == "@ybi.org":
                continue
            local = addr.split("@")[0].lower()
            # Does this address name somebody the roster knows? Any part of
            # their name, or the local part of the address they actually hold
            # — `tom`, `metzinger`, `tmetzinger`, `bewing`, `hruby`.
            # `peer-test` matches nobody and is left alone, which is right:
            # that account is deliberately not on the roster.
            if any(k in local or local in k for k in known if len(k) > 2):
                offenders.append(f"{f.name}:{node.lineno} {addr!r} "
                                 f"(the roster holds no such address)")
    assert not offenders, (
        "a script signs in at an address the roster no longer holds; read "
        "foundation.EMAIL instead, which is derived from ROSTER: "
        + "; ".join(offenders))


def test_the_roster_is_where_the_addresses_come_from():
    """EMAIL is derived, not a second list."""
    import ast

    src = (ROOT / "app" / "foundation.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "EMAIL" for t in node.targets)):
            body = ast.unparse(node.value)
            assert "ROSTER" in body, (
                "foundation.EMAIL no longer reads the roster; it is a second "
                "list of the same people, which is the defect this module is "
                "named after")
            assert "@" not in body, (
                "foundation.EMAIL contains a literal address. It has to come "
                "off the roster, or there are two lists again.")
            break
    else:
        raise AssertionError("foundation.EMAIL is gone")
