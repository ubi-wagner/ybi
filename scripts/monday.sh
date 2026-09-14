#!/usr/bin/env bash
# Pre-flight for a human-in-the-loop Monday.
#
#   YBI_SEED_PASSWORD=... ./scripts/monday.sh            checks only
#   YBI_SEED_PASSWORD=... ./scripts/monday.sh --full     and the rate-stack test
#
# Two halves, and keeping them apart is the whole design.
#
# **The live record is read and never written.** It is sealed, at 100% of the
# 2025 ledger classified, and everything downstream of it is a judgment with
# somebody's name on it: the controller accepts and seals, forty-three people
# adopt and sign their own sheets, Barb decides what goes to NCDMM. A script
# that did any of that would put the machine's name on the seal and throw away
# the one guarantee this system exists to provide.
#
# **The rate stack is proved on a sandbox built from empty.** `--full` creates
# a throwaway database, seeds it, and walks the whole path there — propagation,
# classification, seal, compute, build-up. If the machinery is going to fail it
# fails on the sandbox on Sunday rather than in front of the controller on
# Monday, and the live record is not touched either way.
#
# The order of the drives is not arbitrary. `drive_propagation` seals as its
# third step and proves a sealed set refuses a reclassification as its fourth,
# so it has to run *before* anything else seals — run after, it can do neither
# and reports the guarantee as a fault. `drive_buildup` runs after, because it
# needs a rate to take the carve-outs out from under.
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.
PY=${PY:-python3}
PGHOST=${PGHOST:-127.0.0.1}
PGPORT=${PGPORT:-5433}
PGUSER=${PGUSER:-postgres}
LIVE_DB=${LIVE_DB:-ybi_rec}
SANDBOX_DB=${SANDBOX_DB:-ybi_monday}
SANDBOX_PORT=${SANDBOX_PORT:-8139}
FULL=0
[ "${1:-}" = "--full" ] && FULL=1

bold() { printf '\n\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32mok\033[0m    %s\n' "$1"; }
bad()  { printf '  \033[31m!!\033[0m    %s\n' "$1"; }
fail=0

export DATABASE_URL="postgresql://$PGUSER@$PGHOST:$PGPORT/$LIVE_DB"

# ── half one: the live record, read only ─────────────────────────────

bold "Readiness — the live record, read and not written"
$PY scripts/readiness.py || fail=1

# The eleven control points are in the readiness report above, read straight
# from `v_statement_reconciliation`. Calling `scripts/reconcile.py` here as
# well would be a second reading of one thing — free to disagree with the
# first — and it needs a running API for what is a pure read. The half of
# reconcile.py this cannot do is `--record`, which writes the reconciling
# items, and writing is Monday's job rather than this script's.

if [ "$FULL" -eq 0 ]; then
  bold "Done — checks only"
  printf '  Run with --full to prove the rate stack and propagation on a\n'
  printf '  sandbox built from empty. Nothing above wrote to the record.\n'
  exit $fail
fi

# ── half two: the sandbox ────────────────────────────────────────────

: "${YBI_SEED_PASSWORD:?YBI_SEED_PASSWORD is required for --full}"
SANDBOX_STORE=/var/tmp/ybi_monday_storage
SANDBOX_ENV=/tmp/ybi-monday.env
API_PID=

cleanup() {
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null
  wait "$API_PID" 2>/dev/null
  # Every statement is attempted and a failure is printed rather than
  # raised: a cleanup that stops at the first refusal is worse than none.
  # `WITH (FORCE)` because a run that is interrupted leaves the sandbox API
  # holding connections, and a DROP that waits politely behind them never
  # happens — the next run then meets "database already exists" and stops
  # before it has done anything. A cleanup that only works when nothing went
  # wrong is not a cleanup.
  psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -q \
       -c "DROP DATABASE IF EXISTS $SANDBOX_DB WITH (FORCE)" 2>/dev/null \
    || printf '  note  sandbox %s not dropped\n' "$SANDBOX_DB"
  rm -rf "$SANDBOX_STORE" "$SANDBOX_ENV"
}
trap cleanup EXIT

bold "Building a sandbox from empty — the live record is not touched"
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -q \
     -c "DROP DATABASE IF EXISTS $SANDBOX_DB WITH (FORCE)" \
     -c "CREATE DATABASE $SANDBOX_DB" || { bad "could not create sandbox"; exit 2; }
ok "$SANDBOX_DB created"

mkdir -p "$SANDBOX_STORE"
cat > "$SANDBOX_ENV" <<ENV
DATABASE_URL=postgresql://$PGUSER@$PGHOST:$PGPORT/$SANDBOX_DB
YBI_PERIOD=2025
YBI_ENV=dev
YBI_DEV_SEED=1
YBI_STORAGE_DIR=$SANDBOX_STORE
YBI_SESSION_SECRET=0123456789abcdef0123456789abcdef0123456789abcdef
YBI_JWT_SECRET=0123456789abcdef0123456789abcdef0123456789abcdef
ENV

set -a; . "$SANDBOX_ENV"; set +a
BASE="http://127.0.0.1:$SANDBOX_PORT"
$PY -m uvicorn app.main:app --port "$SANDBOX_PORT" --log-level warning \
    > /tmp/monday-api.log 2>&1 &
API_PID=$!
for _ in $(seq 1 40); do
  curl -fsS "$BASE/api/health" >/dev/null 2>&1 && break
  sleep 0.5
done
if ! curl -fsS "$BASE/api/health" >/dev/null 2>&1; then
  bad "the sandbox API did not start"; tail -15 /tmp/monday-api.log; exit 2
fi
ok "migrations applied, API on :$SANDBOX_PORT"

step() {
  local label="$1"; shift
  if "$@" > /tmp/monday-step.txt 2>&1; then
    ok "$(printf '%-26s %s' "$label" "$(tail -1 /tmp/monday-step.txt)")"
  else
    bad "$(printf '%-26s %s' "$label" "$(tail -1 /tmp/monday-step.txt)")"
    tail -12 /tmp/monday-step.txt | sed 's/^/        /'
    fail=1
  fi
}

bold "The foundation"
step "seed" env BASE="$BASE" YBI_SEED_PASSWORD="$YBI_SEED_PASSWORD" \
     YBI_DEV_SEED=1 ./scripts/seed.sh

bold "Propagation — before anything seals"
# What one reclassification moves, and what it must not. It seals as its
# third step, so it cannot run after the classification below.
step "drive_propagation" $PY scripts/drive_propagation.py --base "$BASE"

bold "The rate stack — before the classification, because it needs work to do"
# `drive_buildup` classifies a group and watches coverage, the pool, the base
# and the rate each move by the right amount. On a record where everything is
# already judged it has nothing to classify and reports COULD NOT RUN —
# which is what the first version of this script did, having applied the 757
# recommendations one step earlier. The drive was right and the order was
# wrong.
step "drive_buildup" $PY scripts/drive_buildup.py --base "$BASE"

bold "The recommendations, applied and sealed — on the sandbox only"
step "classification" $PY scripts/classification_log.py --apply \
     --base "$BASE" --password "$YBI_SEED_PASSWORD"

bold "Readiness on the sandbox — what Monday looks like when it is done"
DATABASE_URL="postgresql://$PGUSER@$PGHOST:$PGPORT/$SANDBOX_DB" \
  $PY scripts/readiness.py || fail=1

if [ "$fail" -eq 0 ]; then
  bold "The stack builds from empty and propagates."
  printf '  The live record is unchanged and still sealed. Everything left is\n'
  printf '  a judgment waiting for the person whose judgment it is.\n'
else
  bold "Something in the stack did not hold. See above."
fi
exit $fail
