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
#   load_registers    everything that is a transcription of a document already
#                     in the image — the effort distribution the fringe base
#                     comes from, YBI's own working calendar and the hours log
#                     under it, the 263-asset register without the funding
#                     column the schedule does not carry, the four awards and
#                     their budget schedules, the text of the agreements. The
#                     list is `app/foundation.py::REGISTERS`, which the boot
#                     walks too, so a recovery brings these back without
#                     anybody running anything
#   load_contract_terms   what the signed agreements actually say, with the
#                     clause each provision came from. Through the API as a
#                     person, which is why it is not on the list above
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
# Everything that is a transcription of a document already in the image: the
# effort distribution, the working calendar and the hours log, the 263-asset
# register, the four awards and their budget schedules, the text of the
# agreements. Seven `run` lines used to stand here, and `app/foundation.py`
# needed the same seven to bring a rebuilt deployment back — two lists of one
# thing, which is the defect that module is named after. The list is
# `foundation.REGISTERS` now and both walk it.
#
# It is run twice on purpose. Two of the seven read the documents, and the
# documents are filed three steps down; a register already in is skipped by
# name, so the second pass costs nothing and picks up exactly those two.
run "the transcriptions" $PY scripts/load_registers.py

step "The awards, and what they say"
# The register is the year, and only the year. This was
# `load_invoices.py` — *"Load the three America Makes invoices"* — which
# loaded exactly that: three, dated 1 May 2026, a sample of the invoice
# format taken before the year's own register existed. Nothing downstream
# asked whether a register of three was the year: four published figures
# were computed off it and three restatements were measured against it.
#
# `load_invoices_2025.py` is the register — 61 invoices, $2,964,077.32, from
# the six PDFs of invoices as issued. Migration `089` removed the three
# examples and `load_awards.py` no longer files them; 2026 billing is entered
# when 2026 is worked.
run "the 2025 invoice register" $PY scripts/load_invoices_2025.py --apply
run "contract provisions" $PY scripts/load_contract_terms.py \
    --base "$BASE" --password "$PASSWORD"

step "The documents"
run "foundational documents" $PY scripts/seed_documents.py \
    --base "$BASE" --password "$PASSWORD"

step "The books against each other"
# After the documents, because it points each award at the agreement it was
# read out of — and the provisions are recorded at step five, before the
# paper arrives. Without it every citation reports NO DOCUMENT on a fresh
# deployment and the check that finds a clause which is not there is silent.
run "the transcriptions, again" $PY scripts/load_registers.py

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
