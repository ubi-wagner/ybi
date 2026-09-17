# The foundation

What is in the record, how it got there, and how to put it back.

Everything below is loaded from source documents YBI supplied. No figure here
was typed in from a summary, and none was invented to make something balance.
This is the whole of the seed data — there will not be more — so it is written
down to the cent and reproduced by one command.

    YBI_SEED_PASSWORD=... BASE=http://127.0.0.1:8000 ./scripts/seed.sh

Twenty-three seconds from an empty database.

## Why this document exists

The contract provisions were read out of four signed agreements by hand —
§4.3 for a ceiling, §10.1 for a term, Schedule B for what indirect was
budgeted, §11.11 for which document governs when two of them disagree. That
work produced twenty-six provisions and they existed in **one developer's
database and in no script**. Seeded from nothing, the award register carried
three contracts and nothing inside them, and an auditor walking back from an
invoice reached the agreement and then a dead end.

Nothing about that was visible from the screens. It took driving the system
from an empty database to find it, which is why the seed is a script now and
why these figures are written down rather than remembered.

## The control totals

Every one of these is reproduced by `./scripts/seed.sh` on an empty database.
A number that does not match after a seed is a defect, not a variation.

### The ledger

| | |
| --- | --- |
| Ledger lines | 15,500 |
| Net movement | 14,371,299.30 |
| Distinct accounts | 188 |
| P&L accounts printed | 127 |

### What there is to classify

| | |
| --- | --- |
| Lines in scope (P&L only) | 5,096 |
| Groups (account × payee) | 999 |
| Scope in absolute dollars | 17,057,405.96 |

Balance sheet movements are **not** in scope. A journal entry moving money
between two accounts is not a cost to classify, and counting both sides of it
inflates the denominator until progress reads as a fraction of what it is.
This is one definition, in `v_classification_coverage`, read by both the
classification screen and the review screens — they used to compute it
separately and answered 13.0% and 2.2% at the same moment.

### Labour

| | |
| --- | --- |
| People on the payroll register | 43 |
| Register wages | 1,835,047.17 |
| Ledger wage accounts | 1,789,993.94 |
| Difference | 45,053.23 |
| Named in reconciling items | 45,053.23 |
| **Unexplained** | **0.00** |
| Effort allocations | 97 |
| Distributed wages | 1,835,047.17 |

The distribution foots to the register exactly. The 45,053.23 is the Bacon
credit sitting in an intern wage account, named rather than netted — it is
the whole of the difference between a fringe rate of 22.45% and one of
21.90%, and Tom has to reclassify it in QuickBooks before either is the
answer.

### The awards

| | | | |
| --- | --- | --- | --- |
| | Ceiling | Cost share | Provisions |
| AM-DRIVE-AM | 1,103,594 | 0 (disputed) | 8 |
| AM-LTM-PROJ88 | 899,500 | 513,065 | 10 |
| AM-HYBRID-P2 | 512,409 | 104,000 | 8 |

Every provision names the clause it came from. A provision with no citation
is somebody's recollection of a contract, which is worth nothing in a dispute
and worse than nothing in a file.

### The invoices

| | | | | |
| --- | --- | --- | --- | --- |
| | Objective | Award | Total | Indirect |
| 10018 | DRIVE-AM | AM-DRIVE-AM | 37,593.90 | **none** |
| 10023 | HYBRID-II | AM-HYBRID-P2 | 1,374.00 | **none** |
| 10039 | LTM | AM-LTM-PROJ88 | 18,993.52 | 3,000.00 |

Fifteen lines across three invoices. Two bill no indirect at all on a base of
38,967.90, and the third's 3,000.00 is a budget draw straight-lined over
twenty-seven months (81,772.76 / 27 = 3,028.62), not a rate applied to
incurred cost. **That pattern is the whole reason the restatement exists.**

### What the zero lines mean

Invoice 10018 carries `TRAVEL 0.00`, `MATERIALS 0.00` and `CONSULTANT 0.00`
in a month when none of those were spent. They are not noise: these invoices
list **the categories the contract allows**, not the categories that had
activity.

Drive AM's Schedule B settles it. Seven categories are named —

| | |
| --- | --- |
| Labor | 583,594 |
| Travel | 40,000 |
| Subcontract | **0** |
| Materials | 5,000 |
| Equipment | **0** |
| Consultant | 60,000 |
| ODC's | 415,000 |
| | **1,103,594** |

— and the invoice carries exactly the five with a non-zero budget. Subcontract
and Equipment, named in the schedule with nothing against them, do not appear
at all. The line set mirrors the budget, and the schedule totals to the
ceiling §4.3 names.

Which makes the most important thing about that invoice a fact about its
*format*: **it has no indirect line because Schedule B has no indirect line.**
Not a biller who forgot, and not a reduced rate or a de minimis election —
no provision at all, against 583,594 of budgeted labour. The document YBI
issued is itself the record of what it was never budgeted to claim, which is
the strongest single piece of evidence the restatement has.

`award_budget` records this (migration `040`), and
`v_invoice_budget_check` compares each invoice's categories to what its award
funds. Only Drive AM's schedule has been transcribed; the other three report
`evaluable = false` rather than passing, because an award nobody has read
cannot fail the check and must not pass it either.

Each invoice is linked to its award. Two were not, and could be walked to an
objective but no further — the link is resolved from the objective now, but
only where exactly one award covers it, because guessing which agreement
authorised an invoice is the kind of inference this system refuses elsewhere.

### The documents

Eighteen foundational documents, 22.3 MB, filed through the real upload route
signed in as a real person so the trail shows who filed them. Content-
addressed, so a second run files nothing twice.

Four executed sub-recipient agreements, two grant agreements, one award
modification, one closeout letter, two audited financial statements, two Form
990 filings, the three QuickBooks exports, the controller's reconciliation
workbook, the asset schedule and the lease schedule.

### The eleven control points

All eleven tie for 2025, with every difference named by a `reconciling_item`
carrying the specific ledger lines it consists of.

The other five periods on file (2021–2024, 2026) report **NO DATA** rather
than tying. That distinction is load-bearing: both sides of most controls are
`COALESCE(..., 0)`, so an empty period compares zero against zero and looks
green. The system reported all eleven points tying over no books at all until
migration `029`.

### The people

Six accounts, provisioned down the ladder through the real API so the audit
trail shows Eric setting up Barb and Barb setting up everybody else.

| | | |
| --- | --- | --- |
| Eric Wagner | `SYSTEM_ADMIN` | no portfolio; reads the record on a written grant |
| Barb Ewing | `ORG_ADMIN` | no portfolio; hands out access |
| Tom Metzinger | `CONTROLLER` | `CONTROLLER` |
| Stephanie Gaffney | `CONTROLLER` | all five portfolios |
| Heidi Ruby | `CONTROLLER` | all five portfolios |
| Engagement Auditor | `AUDITOR` | none; reads everything, writes nothing |

Forty of the forty-three people on the payroll register have **no account**.
The register carries surnames only, so their addresses would have to be
guessed, and an account at a guessed address is one nobody can sign into.
They are surfaced as a gap on the People screen rather than invented.

## The order, and why it is that order

| | |
| --- | --- |
| `provision.py` | Nobody can record anything until there are accounts, and the ladder has to run downward from a bootstrapped root. |
| `load_2025.py` | The ledger, the P&L and the balance sheet — each proving off its own printed subtotals before anything is promoted. |
| `load_registers.py` | Everything that is a transcription of a document already in the image: the effort distribution the fringe base comes from, YBI's own working calendar and the hours log under it, the 263-asset register, the four awards read out of the executed agreements (the ceiling, the term, the rate method and the clause each came from — this was `load_invoices.py`, which also filed three April-2026 example invoices, and `089` removed them), their budget schedules, and the text of the agreements. The list is `app/foundation.py::REGISTERS`, and **the deployment boot walks the same one**, so these seven come back on their own after a Postgres service is rebuilt. Run twice here: two of them read the documents, which are filed three rows down. |
| `load_invoices_2025.py` | The 2025 invoice register — 61 invoices, $2,964,077.32, from the six PDFs of invoices as issued, tied to `3900 Grant Income`. |
| `load_contract_terms.py` | What the signed agreements say, with the clause each provision came from. |
| `seed_documents.py` | The eighteen foundational documents. |
| `reconcile.py --record` | The eleven cross-reference points, every difference named. |

Re-runnable throughout. Everything is content-addressed or checks for itself
first, so a second run loads nothing twice and says so.

**Four of these still need a person, and that is the rule rather than a
gap.** `load_2025.py`, `load_contract_terms.py`, `seed_documents.py`,
`load_projects.py` and `reconcile.py --record` write through the API signed
in as somebody, and `refuse_issued_password` refuses every write from an
account still on the organisation's password — so a boot has nobody to be
and cannot run them. The seven above it can, and do.

## What is deliberately not loaded

Not gaps in the seed — gaps in the engagement, which is a different
conversation:

- **No classifications.** 999 groups, 17,057,405.96, untouched. This is the
  work, and it is Tom's judgment to make. Coverage reads 0.0%.
- **No certifications.** All 43 people await a signature under 2 CFR
  200.430(i), which only they can give.
- **No seal, no rate, no allocation, no restatement.** Each waits on the one
  before it. A rate over an unsealed set is refused with a 409, and that
  refusal is the guarantee the engagement rests on.
- **No square footage.** No building carries area, so the facilities
  carve-out cannot be sized.
- **No asset funding source.** Depreciation on federally funded assets is
  unallowable under 200.436(b) and the register does not say which are.

## Verifying it

```bash
YBI_SEED_PASSWORD=... ./scripts/seed.sh          # the foundation, 23s
YBI_SEED_PASSWORD=... ./scripts/prove.sh         # everything, as real people
YBI_SEED_PASSWORD=... python3 scripts/review_system.py --base $BASE
```

`review_system.py` drives six dimensions as all six people and writes
`docs/SYSTEM_REVIEW.md`. It makes exactly one classification to measure what
a change moves, then walks it back through the real undo route, so it leaves
the record as it found it.
