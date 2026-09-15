#!/usr/bin/env bash
# The foundation, from an empty database, in the order it has to happen.
#
#   YBI_SEED_PASSWORD=... ./scripts/seed.sh
#
# Seven steps were being remembered rather than written down, and the system
# review found what that costs: the twenty-six contract provisions read out of
# the executed agreements existed in one developer's database and in no script,
# so a fresh deployment carried three contracts and nothing inside them.
#
# The order is not arbitrary:
#
#   provision         nobody can record anything until there are accounts, and
#                     the ladder has to run downward from a bootstrapped root
#   load_2025         the ledger, the P&L and the balance sheet, each proving
#                     off its own printed subtotals before anything is promoted
#   load_labor        the effort distribution, which the fringe base comes from
#   load_assets       the 263-asset fixed-asset register, without the funding
#                     column the schedule does not carry, which is the one
#                     thing 200.436(b) waits on
#   load_calendar     YBI's own working calendar and the hours log under it —
#                     261 work days and 2,088 hours in 2025, which is what
#                     every `Allow Hours` in their record is measured against
#   load_invoices     the three America Makes invoices, and the four awards the
#                     register did not have; links each invoice to its award
#   load_contract_terms   what the signed agreements actually say, with the
#                     clause each provision came from
#   load_award_budgets    what each award budgets by category, which is what
#                     decides the line set on an invoice
#   seed_documents    the eighteen foundational documents, filed through the
#                     real upload route as a real person
#   reconcile --record    the eleven cross-reference points, with every
#                     difference named rather than netted
#
# Re-runnable. Everything here is content-addressed or checks for itself
# first, so a second run loads nothing twice and says so.
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.
PY=${PY:-python3}
BASE=${BASE:-http://127.0.0.1:8000}
PASSWORD=${YBI_SEED_PASSWORD:?YBI_SEED_PASSWORD is required}
fail=0

step() { printf '\n\033[1m%s\033[0m\n' "$1"; }

run() {
  local label="$1"; shift
  if "$@" > /tmp/seed-last.txt 2>&1; then
    printf '  ok    %-24s %s\n' "$label" "$(tail -1 /tmp/seed-last.txt)"
  else
    printf '  FAIL  %-24s %s\n' "$label" "$(tail -1 /tmp/seed-last.txt)"
    tail -12 /tmp/seed-last.txt | sed 's/^/        /'
    fail=1
  fi
}

if ! curl -fsS "$BASE/api/health" >/dev/null 2>&1; then
  printf 'nothing serving at %s — start the API and run again\n' "$BASE"
  exit 2
fi

step "The people, down the ladder"
# --dev-password is refused outside a development environment. A real
# deployment runs provision.py on its own and hands out the password sheet.
if [ "${YBI_DEV_SEED:-}" = "1" ]; then
  # On a re-run both the root account and the organisation's administrator
  # are already on passwords they chose, and provision.py refuses to reset a
  # password somebody is using — correctly, because silently replacing one is
  # how an account stops belonging to a person. Passing them back is what
  # makes the seed re-runnable, and in development they are the same shared
  # password every account got.
  export YBI_ROOT_PASSWORD="${YBI_ROOT_PASSWORD:-$PASSWORD}"
  export YBI_ORG_ADMIN_PASSWORD="${YBI_ORG_ADMIN_PASSWORD:-$PASSWORD}"
  run "provision" $PY scripts/provision.py --base "$BASE" \
      --dev-password "$PASSWORD"
else
  run "provision" $PY scripts/provision.py --base "$BASE"
fi

step "The books"
run "ledger, P&L, sheet" $PY scripts/load_2025.py --base "$BASE"
run "effort distribution" $PY scripts/load_labor.py
# The calendar and the hours behind that distribution. After it, because the
# hours log maps its objective headings through labor_objective_map, and the
# cost objectives have to exist first.
run "calendar and hours log" $PY scripts/load_calendar.py
# The fixed-asset register, from the schedule YBI already holds. It is
# transcription and not judgment — their own depreciation schedule, read as
# printed, which is why it belongs beside the ledger's loader and not in the
# application. The funding column is deliberately not loaded: the schedule
# does not have one, which is 200.313(d)(1) unanswered and is exactly what
# Heidi answers on Classify > Equipment.
run "fixed-asset register" $PY scripts/load_assets.py

step "The awards, and what they say"
run "invoices and awards" $PY scripts/load_invoices.py
run "contract provisions" $PY scripts/load_contract_terms.py \
    --base "$BASE" --password "$PASSWORD"
run "budget schedules" $PY scripts/load_award_budgets.py

step "The documents"
run "foundational documents" $PY scripts/seed_documents.py \
    --base "$BASE" --password "$PASSWORD"

step "The books against each other"
# After the documents, because it points each award at the agreement it was
# read out of — and the provisions are recorded at step five, before the
# paper arrives. Without it every citation reports NO DOCUMENT on a fresh
# deployment and the check that finds a clause which is not there is silent.
run "agreements and their text" $PY scripts/read_documents.py --write
run "awards to their agreements" $PY scripts/link_agreements.py

# After the awards and the payroll, because a project hangs off a charge code
# that exists, names the award it works under, and takes its team from the
# distribution that actually put people on it.
run "projects and their managers" $PY scripts/load_projects.py --base "$BASE"

run "eleven control points" $PY scripts/reconcile.py --base "$BASE" --record

if [ "$fail" -eq 0 ]; then
  printf '\n\033[1mThe foundation is in.\033[0m Run ./scripts/prove.sh next.\n'
else
  printf '\n\033[1mSomething did not load.\033[0m See above.\n'
fi
exit $fail
