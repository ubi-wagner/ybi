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

step "The engine, and the structure of the code"
run "unit and domain tests" $PY -m pytest -q

if ! curl -fsS "$BASE/api/health" >/dev/null 2>&1; then
  printf '\n  nothing serving at %s — start the API and run again\n' "$BASE"
  exit 2
fi

step "The three source documents against each other"
run "schedule A-1 reconciliation" $PY scripts/reconcile.py --base "$BASE"

step "Every person, every process, every change on the record"
run "drive_everyone" $PY scripts/drive_everyone.py --base "$BASE"

step "The boundaries"
run "drive_access" $PY scripts/drive_access.py --base "$BASE"
run "drive_actors" $PY scripts/drive_actors.py --base "$BASE"

step "The manual"
run "screenshots are current" $PY scripts/walk_manuals.py --base "$BASE"
run "manual tests" $PY -m pytest -q tests/test_manual.py

if [ "$fail" -eq 0 ]; then
  printf '\n\033[1mEverything proved.\033[0m\n'
else
  printf '\n\033[1mSomething did not.\033[0m See the findings above.\n'
fi
exit $fail
