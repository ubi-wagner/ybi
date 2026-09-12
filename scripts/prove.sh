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

step() {
  printf '\n\033[1m%s\033[0m\n' "$1"
}

run() {
  local label="$1"; shift
  if "$@" > /tmp/prove-last.txt 2>&1; then
    printf '  PASS  %-34s %s\n' "$label" "$(tail -1 /tmp/prove-last.txt)"
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

step "The engine, and the structure of the code"
run "unit and domain tests" $PY -m pytest -q

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

step "Every person, every process, every change on the record"
run "drive_everyone" $PY scripts/drive_everyone.py --base "$BASE"

step "A piece of work set up, approved, and handed on"
run "drive_projects" $PY scripts/drive_projects.py --base "$BASE"

step "The income side — charge codes, contracts, milestones, money in"
run "drive_contracts" $PY scripts/drive_contracts.py --base "$BASE"

step "The same chain, walked backwards"
run "drive_reverse" $PY scripts/drive_reverse.py --base "$BASE"

step "The boundaries"
run "drive_access" $PY scripts/drive_access.py --base "$BASE"
run "drive_actors" $PY scripts/drive_actors.py --base "$BASE"

if [ "$fail" -eq 0 ]; then
  printf '\n\033[1mEverything proved.\033[0m\n'
else
  printf '\n\033[1mSomething did not.\033[0m See the findings above.\n'
fi
exit $fail
