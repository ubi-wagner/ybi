"""Two doors that were not there: a shelf of manuals, and a way to get in.

The manuals existed as files in `docs/` and, once the boot started filing
them, as rows in a register an employee may not read. So the person the
everybody manual is written for — somebody with a timesheet and no portfolio
— could not reach it at all, which is the capability-with-no-door shape one
level along: the content was complete and nothing served it to its reader.

The other door is registration. Thirty-seven of the forty-three people on
the 2025 payroll have no account and every one of them has to sign their own
200.430(i) certification; the only path to an account was an administrator
typing in an address and handing out a password.

Every source-reading assertion here was watched failing against a
deliberately broken copy.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = (ROOT / "app" / "routers" / "documents.py").read_text()
AUTH = (ROOT / "app" / "routers" / "auth.py").read_text()
APP = (ROOT / "web" / "src" / "App.jsx").read_text()
SIGNIN = (ROOT / "web" / "src" / "pages" / "SignIn.jsx").read_text()
API = (ROOT / "web" / "src" / "api.js").read_text()


def handler(src: str, name: str) -> str:
    """One handler's **code**, with its docstring and comments removed.

    The first draft took the text from `def` to the next top-level statement
    and three assertions failed against correct code, every one of them on a
    word inside the docstring — `require_reader` in a sentence saying why it
    is deliberately not used, `provisioned_by` in a paragraph explaining why
    it stays NULL. A test that reads prose is testing prose, and it fails
    hardest on the handlers that explain themselves best.

    `ast.unparse` of the body with the docstring dropped is the code and
    nothing else: comments do not survive a parse, and neither does the
    docstring once it is removed.
    """
    tree = ast.parse(src)
    node = next(n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == name)
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        node.body = node.body[1:]
    # The whole node, decorators and signature included — the gate a route
    # takes is in `Depends(...)` in the signature, and a version of this
    # that returned only the body could not see it.
    return ast.unparse(node)


# ── The shelf ────────────────────────────────────────────────────────

def test_the_guidebook_has_a_door_and_the_screen_uses_it():
    """A route with no call in the SPA is the defect this repository has
    found four times: the restatement, the timesheet draft, the lane
    comparison and `POST /api/rates/compute`."""
    assert '@router.get("/guides")' in DOCS
    assert 'req("/documents/guides")' in API
    assert 'api.guides()' in (ROOT / "web" / "src" / "pages" / "Guidebook.jsx").read_text()
    assert '"/guidebook"' in APP and "Guidebook" in APP


def test_the_guidebook_is_not_gated_on_reading_the_cost_record():
    """`require_reader` would be wrong in the direction that costs the most.

    The everybody manual is written for somebody with a timesheet and no
    portfolio, and reading the cost record is a grant they do not have.
    Nothing on any of these pages is part of the cost record.
    """
    body = handler(DOCS, "guides")
    assert "Depends(current_actor)" in body
    assert "require_reader" not in body and "require_office" not in body


def test_the_nav_asks_for_what_the_api_asks_for():
    """A nav stricter than the API hides work; a looser one offers a 403.
    The route takes `current_actor`, so the tab takes `null`."""
    row = re.search(r'\["/guidebook",[^\]]*\]', APP).group(0)
    assert row.rstrip("]").rstrip().endswith("null"), row


def test_yours_orders_the_shelf_and_never_shortens_it():
    """An employee who cannot see that a controller's manual exists learns
    the shelf is short, which is the nav-stricter-than-the-API defect in
    another costume. The handler must not filter on `yours`."""
    body = handler(DOCS, "guides")
    assert "out.sort(" in body, "the shelf is not ordered at all"

    # Structural rather than textual, because the rule is about control
    # flow: every row read is appended, unconditionally. A first draft
    # asserted `not re.search(r"WHERE[\s\S]*yours")`, which matched the
    # SELECT's own WHERE and the `yours` key in the return and so could only
    # ever fail — an assertion that argues against working code.
    node = next(n for n in ast.walk(ast.parse(DOCS))
                if isinstance(n, ast.FunctionDef) and n.name == "guides")
    loops = [n for n in ast.walk(node) if isinstance(n, ast.For)]
    assert len(loops) == 1, "the shelf is built by more than one loop"
    loop = loops[0]
    assert not [n for n in ast.walk(loop) if isinstance(n, ast.Continue)], (
        "the guides loop skips a row")
    appends = [st for st in loop.body
               if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call)
               and getattr(st.value.func, "attr", "") == "append"]
    assert appends, ("nothing is appended at the top level of the loop, so "
                     "a guide reaches the shelf conditionally")


def test_rank_and_portfolio_are_read_apart():
    """`CONTROLLER` names a portfolio *and* a rank, and a draft that fell
    through to `"CONTROLLER" in held` for anything it did not otherwise
    match handed the controller the auditor's manual as his own. The
    portfolio that reaches every screen does not make somebody the auditor.
    """
    body = handler(DOCS, "guides")
    assert "Portfolio.__members__" in body, (
        "the audience is not tested against the portfolio enum, so a role "
        "and a portfolio of the same name cannot be told apart")
    assert "audience == actor.role" in body


def test_a_guide_is_readable_by_anybody_signed_in_and_nothing_else_is():
    """The widening is one kind wide. An employee's receipt is not public to
    the organisation because a manual is."""
    body = handler(DOCS, "download")
    assert "foundation.GUIDE_KIND" in body
    assert "not actor.can_read" in body, (
        "the download gate no longer consults can_read at all")


# ── The way in ───────────────────────────────────────────────────────

def test_registration_takes_the_organisation_password_and_never_stores_one():
    """`YBI_INITIAL_PASSWORD` is the invitation and stays a setting. A row
    carrying it would put one secret at rest in forty places."""
    body = handler(AUTH, "register")
    assert "shared_initial_password()" in body
    assert "unusable_password_hash()" in body
    assert "hash_password(" not in body, (
        "register hashes something — the only hash it may write is the "
        "random one nobody holds")


def test_registration_cannot_raise_on_a_non_ascii_password():
    """`secrets.compare_digest` refuses two `str` arguments where either is
    non-ASCII — it raises TypeError. A 500 where a 403 belongs is a sharper
    oracle than the one being avoided, and this is the second place in the
    codebase to make that comparison."""
    body = handler(AUTH, "register")
    # ast.unparse normalises quoting, so the assertion cannot carry any.
    assert "encode('utf-8')" in body, "the comparison is made on str"
    assert "except BaseException" in body


def test_registration_is_throttled_like_a_sign_in():
    """One password opens every unclaimed account, so a series of guesses
    against this endpoint is worth more than a series against one person's."""
    body = handler(AUTH, "register")
    assert "recent_login_failures" in body and "MAX_FAILURES" in body
    assert "login_attempt" in body, (
        "a refused registration is not counted, so the throttle above it "
        "can never fire")


def test_registration_grants_no_authority():
    """The account is a timesheet, a certification and an inbox. Authority
    stays a grant somebody makes, and is recorded when it is."""
    body = handler(AUTH, "register")
    assert "'EMPLOYEE'" in body
    assert "actor_portfolio" not in body, "register grants a portfolio"
    assert "record_access" not in body, "register grants access to the record"
    for rank in ("SYSTEM_ADMIN", "ORG_ADMIN", "AUDITOR"):
        assert rank not in body, f"register can create a {rank}"


def test_registration_never_takes_a_payroll_identity_somebody_holds():
    """Two rows for one person is how a timesheet and a certification come
    apart. A derived key is allowed; a key already held is a 409."""
    body = handler(AUTH, "register")
    assert re.search(r"SELECT 1 FROM actor WHERE employee_key", body), (
        "register does not check whether the key is already held")


def test_the_account_is_not_provisioned_by_anybody():
    """Nobody provisioned it, and the roster shows it as such. Naming an
    administrator would put her signature on an act she was not present
    for."""
    body = handler(AUTH, "register")
    assert "provisioned_by" not in body


def test_the_registration_is_written_down_with_where_it_came_from():
    """Everybody inside YBI holds the same organisational password this
    round, so the act has to be visible: auto-approved, recorded, and
    reversible by deactivating the account."""
    body = handler(AUTH, "register")
    assert "audit_log" in body and "ACTOR_CREATE" in body
    assert "{ip}" in body, "the audit row does not say where it came from"


def test_registering_signs_in_through_the_ordinary_door():
    """Nothing about the session, the throttle, the SIGN_IN_SHARED row or
    the must-set-password gate is special-cased for a registration, because
    none of it should be."""
    body = handler(AUTH, "register")
    assert "return login(" in body
    assert "issue_token" not in body and "actor_session" not in body, (
        "register issues its own session instead of signing in")


def test_the_sign_in_screen_offers_both_doors_and_keeps_them_apart():
    """Sign in and open an account want the same two boxes and mean opposite
    things by the password. A form that quietly did one or the other would
    tell somebody they registered when they signed in as a colleague."""
    assert "api.register(" in SIGNIN and "api.login(" in SIGNIN
    assert "signin-tabs" in SIGNIN
    assert 'setMode' in SIGNIN


def test_only_the_registration_error_says_why():
    """A sign-in error that distinguished an unknown account from a wrong
    password would enumerate the organisation. A registration refusal is the
    opposite case — the person needs to know which of three reasons it was."""
    assert 'explain(err)' in SIGNIN
    assert SIGNIN.count("Email or password is incorrect.") == 1
