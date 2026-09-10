# YBI Cost Allocation

Turn the QuickBooks general ledger into defensible 2 CFR 200 cost pools, indirect
rates, contract allocations and an audit package.

Built for the 2025 Form 990 and audit, and for justifying cost recovery on 2026+
cost-reimbursement proposals.

## Quick start

```bash
git clone <this repo> && cd ybi-cost
cp .env.example .env
./scripts/dev.sh
```

API on http://localhost:8000 (docs at `/api/docs`), UI on http://localhost:5173.

## Deploy to Railway

1. Push to GitHub.
2. New Railway project → Deploy from GitHub repo. It picks up the `Dockerfile`.
3. Add a **Postgres** service in the same project. `DATABASE_URL` is injected.
4. Add a volume mounted at `/srv/storage` for uploaded documents.
5. First boot runs the migrations and seeds the period, objectives and the
   Hybrid Phase 2 award terms.

Healthcheck is `/api/health`.

## The workflow

**Import** — Upload the QBO General Ledger. It is parsed under a named profile,
then reconciled against QuickBooks' own printed `Total for ...` rows. Nothing
reaches the ledger until every account subtotal ties; a database trigger enforces
it, not just the handler.

**Classify** — Work grouped by account and vendor, largest dollars first. Roughly
750 groups, of which the top 200 carry ~95% of the money. Each arrives with a
proposal drawn from QuickBooks' `Customer:Job` field, the account name, or last
year's treatment. Four independent dimensions per decision — cost pool, Form 990
function, federal treatment, cost objective — because 990 Part IX and 2 CFR 200
Subpart E ask different questions and one field cannot answer both.

Progress is measured in **dollar coverage**, not row count. No rate is shown here.

**Seal** — Hash every classification and freeze the set. This is what makes the
rate defensible: it can be shown to be a consequence of the judgments rather
than a target they were fitted to.

**Rates** — Multiple allocation base method, 2 CFR 200 Appendix IV B.3. Fringe on
wages; overhead and G&A on MTDC. Carve-outs (tenant space, federally funded
depreciable basis) each require a citation, an amount, a driver and an evidence
grade.

**Lanes** — Fork a scenario to test alternative classifications without touching
the baseline. Assumption variants are free; classification overrides require a
reason and are disclosed in the audit package. Exploration stays visible.

**Awards** — Claimable versus billed per award, with every contract constraint
evaluated and cited. All blocking constraints pass, and a restated invoice is
issuable. One fails, and the system records an acknowledged deficiency instead.

**Export** — Eight schedules with live formulas, traceable to the ledger.

**Chart** — The 2026 QuickBooks chart of accounts, classes and customer:jobs,
exportable as QBO import files, plus a crosswalk proving it carries every
dollar of the reconciled 2025 ledger. Account number carries the cost pool, so
from 2026 classification is arithmetic rather than judgment.

## Context

`PLAN.md` is the current execution plan — phases, tasks and the tie-out that
says each one is done.

`BRIEF.md` is the orientation — what YBI is, why the accounting drifted,
the deployment shape, DCAA alignment, and the raw intake manifest.

`PROJECT_CONTEXT.md` carries the engagement findings — verified control totals,
the labor position, the recommended rate model, the America Makes reconciliation
and every open item with its owner. Read it before touching the cost logic; the
numbers in it are recomputed from source, not quoted from anyone's summary.

## Design notes

`CLAUDE.md` has the working conventions. Two are load-bearing:

- **Money is `Decimal`.** Never float.
- **Invariants live in the schema.** Source ledger lines cannot be updated or
  deleted, a rate cannot exist without a matching seal, an invoice cannot be
  issued while a blocking constraint fails. Those hold even when application
  code is wrong, which is the only kind of guarantee worth having in front of an
  auditor.

## Status

Domain engine is complete and tested against the real 2025 ledger: reconciliation
variance $0.00, allocation variance $0.00, four controls passing. The API and UI
are a working strawman — the classification queue is functional; rate computation
and audit package download still need wiring.

Not legal or audit advice.
