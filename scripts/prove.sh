#!/usr/bin/env bash
# Everything, in the order a reviewer would want it.
#
#   YBI_SEED_PASSWORD=... ./scripts/prove.sh
#
# The unit tests need no database. Everything after them drives the running
# service as real people against real rows, because a permission claim and an
# audit claim are worth what they are tested at.
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.
PY=${PY:-.venv/bin/python}
BASE=${BASE:-http://127.0.0.1:8000}
fail=0
unevaluable=0

step() {
  printf '\n\033[1m%s\033[0m\n' "$1"
}

# Three states, not two — the control register's, applied to the harness.
#
# A drive exits **2** when its precondition is absent: `drive_recertify` needs
# a certified rate, `drive_restage` a record the classification log has
# written, `drive_partitions` a sealed set. None of those exist after a bare
# `seed.sh`, because classifying and sealing are judgments and no script here
# makes one. So on a database built from empty three drives printed
# **COULD NOT RUN** and this rendered all three as `FAIL`, and the run ended
# *"Something did not"* over a system with nothing wrong with it.
#
# That is `029` pointed at the proof harness: **a control that cannot be
# evaluated has not passed, and it has not failed either.** And the cost is
# the one this repository keeps paying — a harness going red for a reason
# that is not a defect is how a reader learns to ignore it, and then to
# ignore the run that finds something.
#
# `1` is still a finding and still fails the run.
run() {
  local label="$1"; shift
  local code=0
  "$@" > /tmp/prove-last.txt 2>&1 || code=$?
  if [ "$code" -eq 0 ]; then
    printf '  PASS  %-34s %s\n' "$label" "$(tail -1 /tmp/prove-last.txt)"
  elif [ "$code" -eq 2 ]; then
    printf '  ----  %-34s %s\n' "$label" \
      "$(grep -m1 'COULD NOT RUN' /tmp/prove-last.txt || tail -1 /tmp/prove-last.txt)"
    unevaluable=$((unevaluable + 1))
  else
    printf '  FAIL  %-34s %s\n' "$label" "$(tail -1 /tmp/prove-last.txt)"
    sed -n '/FINDING\|FAIL\|Error/p' /tmp/prove-last.txt | head -12
    fail=1
  fi
}

# Before anything, because a stale interpreter fails two thousand checks in
# later and reads like a defect in the system. drive_access ended a clean run
# with "ModuleNotFoundError: No module named 'pypdf'" printed under
# **The boundaries**, which is where a reader looks for a broken permission
# gate — the venv simply predated the dependency.
if ! $PY - <<'PREFLIGHT' 2>/dev/null
# `import importlib` alone does not bind `importlib.util` — the first
# draft of this did exactly that, raised AttributeError, exited non-zero
# and told every reader their environment was broken. A guard that always
# fires is worse than no guard.
import importlib.util
import sys
missing = [m for m in ("fastapi", "psycopg", "httpx", "openpyxl", "pypdf",
                       "reportlab", "pytest")
           if importlib.util.find_spec(m) is None]
sys.exit(1 if missing else 0)
PREFLIGHT
then
  printf '\n  %s is missing something it needs.\n' "$PY"
  printf '  This is the environment, not the system:\n\n'
  printf '      %s -m pip install -r requirements.txt\n\n' "$PY"
  exit 2
fi

# And the database the drives read directly, for the same reason one line up.
#
# Every drive below talks to the API over `--base` **and** reads rows through
# `app.db`, so it needs `DATABASE_URL` as well as a running service. Nothing
# here named it. Run without one and `app/settings.py` falls back to `.env` —
# which on a machine that is not the one `.env` was written for points at a
# socket that does not exist — and `psycopg_pool` answers a caller that can
# never connect with **`PoolTimeout: couldn't get a connection after 30.00
# sec`**, swallowing the connection error that would have said why.
#
# So twelve drives go red in a row, each naming a pool timeout, and none of
# them names the variable. That is `YBI_JWT_SECRET` in a second place: the
# worst shape a configuration fault can take is one that reports as something
# else, and a proof harness going red for a reason that is not a defect is
# how a reader learns to ignore it.
#
# One connection, before anything, and it says which URL it tried.
if ! $PY - <<'DBCHECK' 2>/tmp/prove-db.txt
import sys

import psycopg

from app.settings import settings

# Deliberately not `app.db`: its pool retries in the background and prints
# a line per attempt, so the one fact worth reading — which URL, and what
# the server said — arrives eight times and under eight copies of itself.
# One connection, one answer.
try:
    with psycopg.connect(settings.database_url, connect_timeout=5) as con:
        con.execute("SELECT 1")
except Exception as exc:                       # noqa: BLE001 - reported below
    first = str(exc).strip().splitlines()[0]
    print(f"tried  {settings.database_url}\n{first}", file=sys.stderr)
    sys.exit(1)
DBCHECK
then
  printf '\n  the database is not reachable.\n'
  printf '  This is the environment, not the system:\n\n'
  sed 's/^/      /' /tmp/prove-db.txt
  printf '\n      DATABASE_URL=postgresql://... %s\n\n' "$0"
  exit 2
fi

step "The engine, and the structure of the code"
# `tests/test_manual.py` is deliberately excluded here and run on its own
# below, **after** the walk that produces what it asserts on. Running it
# twice was not the problem; running it first was: it reads the manifest
# `walk_manuals.py` writes three steps later, so a run whose previous walk
# had been interrupted failed on an artefact this same script was about to
# regenerate — a test arguing against working code, in the one place a
# reviewer looks to decide whether the system holds.
run "unit and domain tests" $PY -m pytest -q --ignore=tests/test_manual.py

if ! curl -fsS "$BASE/api/health" >/dev/null 2>&1; then
  printf '\n  nothing serving at %s — start the API and run again\n' "$BASE"
  exit 2
fi

step "The three source documents against each other"
run "schedule A-1 reconciliation" $PY scripts/reconcile.py --base "$BASE"

step "The manual"
# Before the drives, not after. The drives put fixtures on screens the manual
# photographs, and a new person should not open the Space chapter to find a
# building called "Drive Test Building".
run "screenshots are current" $PY scripts/walk_manuals.py --base "$BASE"
run "manual tests" $PY -m pytest -q tests/test_manual.py

step "The system as a state machine, one action at a time"
# Before everything, because it needs the record at rest: every expectation in
# it is an absolute count from a known start. It walks its own turns back and
# leaves the live state exactly as it found it.
run "drive_state_machine" $PY scripts/drive_state_machine.py --base "$BASE"

step "The whole system, as everybody, in six dimensions"
# Before the drives, for the same reason the manual walk is: the drives seal
# the decision set, and a sealed set refuses the one classification this
# makes to measure what a change propagates. It walks that change back
# afterwards, so it leaves the record as it found it.
run "system review" $PY scripts/review_system.py --base "$BASE"

step "What one change moves, and what it must not"
# Before every drive that seals, because its third step is to seal and its
# fourth is to prove a sealed set refuses a reclassification. Run after
# drive_everyone it can do neither, and reports a correct refusal as a fault.
run "drive_propagation" $PY scripts/drive_propagation.py --base "$BASE"

step "What is still being asked for, and the answer coming back"
# Before the drives that seal, like the others: it writes assets, space and
# addresses, none of which the seal covers, but it does classify nothing and
# leaves the decision set exactly as it found it.
run "drive_requests" $PY scripts/drive_requests.py --base "$BASE"

step "A folder of documents, matched to the cost they support"
# Before the drives that seal. Its last step makes a judgment citing the
# document it matched, to prove the grade the whole matcher exists to reach,
# and a sealed set correctly refuses that — so run after one it reports the
# guarantee as a gap. It walks every document and attachment back itself.
run "drive_evidence" $PY scripts/drive_evidence.py --base "$BASE"

step "Two people, one record, the same instant"
# With drive_propagation, and for the same reason: it seals, and it proves a
# sealed set refuses a judgment that was already in flight. It leaves the set
# open and its own judgments reversed, so the drives after it start where they
# expect to.
run "drive_concurrency" $PY scripts/drive_concurrency.py --base "$BASE"

step "The rate build-up, and everything that moves it"
# With the drives that seal, and before drive_everyone, which expects an open
# set. It seals, computes, judges, recomputes and unseals, and its last step
# takes the carve-outs out from under a live rate to prove the tie control
# can fail — so it must run where it can seal freely and put the record back.
run "drive_buildup" $PY scripts/drive_buildup.py --base "$BASE"

step "The auditor rejects a classification inside a sealed, certified set"
# After drive_buildup, because it needs a rate to certify and drive_buildup is
# what leaves one. It certifies, withdraws, unseals, reclassifies, re-seals,
# recomputes and re-certifies — then puts every one of those back, checked
# against a census of the pools taken before it started. The cycle an auditor
# actually triggers, and until this existed nobody had walked it end to end.
run "drive_recertify" $PY scripts/drive_recertify.py --base "$BASE"

step "A restaged year: a note, a recommendation, an adoption"
# After drive_recertify, because it needs a sealed set to be refused by — its
# sharpest check is that accepting an auditor's recommendation under a seal is
# refused by the seal, in the seal's own words, since there is no second path
# to the cost record for the ask to travel down. It runs against whatever
# working positions the record carries and reports COULD NOT RUN where there
# are none, rather than manufacturing some to measure.
run "drive_restage" $PY scripts/drive_restage.py --base "$BASE"

step "Heidi measures, Tom verifies, and the carve-out fires"
# After drive_restage, which is the same mechanism pointed at classification.
# This is the pair the walk reports as NO DATA — the square footage the 200.465
# carve-out is sized by, and the funding source 200.436(b) turns on — proposed
# by the portfolio that holds them and accepted by the controller who signs the
# rate they feed. It puts its building back and says what it could not.
run "drive_partitions" $PY scripts/drive_partitions.py --base "$BASE"

step "Every person, every process, every change on the record"
run "drive_everyone" $PY scripts/drive_everyone.py --base "$BASE"

# After the drives that seal. A restatement is a consequence of the rate and
# the rate of the judgments, so a drive that sealed to give itself something
# to measure would be reading its own writing — this one computes over a seal
# somebody else applied and refuses to make one. Note that sealing is not the
# same as leaving a rate live: drive_state_machine seals, computes and then
# unseals, which supersedes every rate. The drive reads the state rather than
# assuming what the script before it left behind.
step "The number walked out to NCDMM"
run "drive_restate" $PY scripts/drive_restate.py --base "$BASE"

step "A piece of work set up, approved, and handed on"
run "drive_projects" $PY scripts/drive_projects.py --base "$BASE"

step "The income side — charge codes, contracts, milestones, money in"
run "drive_contracts" $PY scripts/drive_contracts.py --base "$BASE"

step "The same chain, walked backwards"
run "drive_reverse" $PY scripts/drive_reverse.py --base "$BASE"

step "The boundaries"
run "drive_access" $PY scripts/drive_access.py --base "$BASE"
run "drive_actors" $PY scripts/drive_actors.py --base "$BASE"

if [ "$fail" -eq 0 ] && [ "$unevaluable" -eq 0 ]; then
  printf '\n\033[1mEverything proved.\033[0m\n'
elif [ "$fail" -eq 0 ]; then
  printf '\n\033[1mEverything that could be evaluated proved.\033[0m\n'
  printf '  %d step(s) had no precondition to run against — a bare seed\n' \
    "$unevaluable"
  printf '  carries no classification and no seal, because both are\n'
  printf '  judgments and nothing here makes one. Apply the classification\n'
  printf '  log and seal, then run those again.\n'
else
  printf '\n\033[1mSomething did not.\033[0m See the findings above.\n'
fi
exit $fail
