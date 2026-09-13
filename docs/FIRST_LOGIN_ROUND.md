# The shared first-login round

Forty of the forty-three people in the payroll distribution have no account.
Opening forty accounts with forty individually-chosen passwords means handing
out forty secrets; this is the other way — **one password for the round, which
every person replaces with their own the first time they sign in.**

The mechanism the system already had is the half that matters:
`refuse_issued_password` refuses **every write** from an account whose password
it did not choose itself. A classification, a timesheet, a certification, a
document — all refused, with the one exception of changing your own password.
So a shared first-login password cannot put an unclaimed signature on the
record. What was missing was only a way to *issue* one.

## Set it

One Railway variable on the API service:

    YBI_INITIAL_PASSWORD = <at least 12 characters>

Then redeploy. Nothing else changes: with the variable empty, the system
behaves exactly as it did before.

## What it does

    Barb opens an account, naming no password
      -> the account is opened on the shared one (opened_on: SHARED_INITIAL)
    the person signs in with it
      -> recorded as SIGN_IN_SHARED, not SIGN_IN
      -> the screen puts "Choose your own password" in front of everything
      -> every write is refused: PASSWORD_NOT_YOUR_OWN
    they choose their own
      -> the shared password stops opening their account, then and there
      -> everything works normally

`POST /api/auth/actors` now takes **no** `password` field and opens the account
on the shared value. Passing one still works and still means *this password,
for this person*.

## The three properties worth knowing

**The shared value is never stored against anybody's row.** Each account gets a
random hash nobody holds; login accepts the *setting* in addition, for accounts
that have not set their own. Three things follow:

- **Clearing the variable withdraws it from everybody still on it, at once.**
  No password resets, no re-provisioning. Verified live: the same account and
  the same password answer 200 against a service holding the variable and 401
  against one that does not.
- **Rotating it is one change**, not forty.
- **A copy of the database is not a copy of the credential.**

**It closes person by person as the round completes.** An account that has
chosen its own password stops accepting the shared one immediately — so the
window narrows on its own as people sign in, without anybody tracking it.

**It is not an account-enumeration oracle.** The shared password against an
address with no account answers exactly what a wrong password against a real
one answers: 401. This system knows the names of everyone at the organisation,
so a credential that distinguished the two would hand over the roster.

## The exposure, stated plainly

**While the variable is set, anybody who has the value can claim any account
that has not yet been claimed.** That is inherent in a shared password and no
implementation removes it. What bounds it:

- an unclaimed account can **write nothing**, so the worst case is somebody
  taking an account rather than forging a record through one;
- the window is per-person and closes the moment they sign in;
- every sign-in on it is `SIGN_IN_SHARED` on the audit trail, so "who was on
  the shared credential, and when" is answerable afterwards;
- the People screen shows who still holds it (`holds_bootstrap_password`).

So: **set it for the round, and clear it when the round is done.** Tell people
the round is running and ask them to sign in promptly — the value of the
variable is not the secret that matters, the speed of claiming is.

## Checking it

The unit tests hold `check_credential` — which credentials authenticate, and
which must not. They run without a database:

    pytest -q tests/test_shared_initial_password.py

The end-to-end walks the whole round through the real API against real rows —
opening an account, signing in on the shared password, being refused a write,
claiming it, and the shared password then failing:

    YBI_INITIAL_PASSWORD=... YBI_SEED_PASSWORD=... \
        python3 scripts/drive_shared_password.py --base https://<your-service>

It stands its probe account down afterwards and checks the roster is the size
it started at.

## What is still to come

The forty accounts need forty email addresses, and **those arrive with the
roster reply** — the same reply that carries the employment terms. So the
sequence is: reply comes back → accept it → open the accounts → people claim
them → people certify. Opening them one at a time on the People screen works
today; a bulk opener is worth writing once the reply's shape is known rather
than guessed at.
