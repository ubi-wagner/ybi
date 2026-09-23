# Rising Tides — what the record says, and what it cannot say

*2025 · generated 23 September 2026 from `ybi_exam`*

> **NOT CERTIFIED — nobody has put their name to the rate these figures rest on.**
> **The rate has been recomputed since it was certified, so the signature is on a build-up that no longer stands. Sign the new one. Nothing here is blocked by that: this is a working document, and it says so rather than waiting.**

Generated from the live record by `scripts/rising_tides.py`. Every figure is read from the row that owns it; nothing here is recalled and nothing is derived twice. **It decides nothing** — the question at the end of it is a judgment about a document nobody here has read.

## 1. The question

Is Rising Tides a federal award?

The controller's workbook says yes. `cost_objective.is_federal` says **no**. Both readings are on the record and they have never been reconciled — it is on this repository's own open-questions list, and it is what Tom's audit turns on.

The invoices make the tension concrete rather than theoretical: all 9 of them are billed to the **Appalachian Regional Commission**, and ARC POWER is a federal programme. Billing a federal agency is not the same fact as holding a federal award — a fee-for-service contract and a subaward are billed to the same place and land in different columns — so the instrument decides it, and the instrument is not here.

## 2. What the record holds

| | |
| --- | ---: |
| `cost_objective.is_federal` | **false** |
| CFDA / ALN | — none recorded |
| objective type | PROGRAM |
| award row | **none — no award is on the register** |
| 2025 invoices | 9 |
| billed | 937,073.07 |
| `3900 Grant Income:Rising Tides` | 804,270.03 |
| the anchor | **OPEN**, by 132,803.04 |
| judged DIRECT / NOT_APPLICABLE | 33 groups · **582,085.53** |
| distributed wages | 106,398.41 across 7 people |

Every judged dollar sits in one account — `Grant Expenses:Rising Tides Expense` — which is the 2025 chart burying programme identity in an account *name*, the structural defect the 2026 chart fixes.

## 3. What is not on the record, and each one matters

**A blank is unanswered, and unanswered is a value.** None of these is a gap to fill in with a reasonable guess:

- **No award row.** The register carries four awards and Rising Tides is not one of them, so there is no ceiling, no period of performance, no rate method and no clause to cite. Every constraint test the system runs against an award is unevaluable here — and *unevaluable is not a pass*.
- **No agreement on file.** Nothing in the document register names Rising Tides or the Appalachian Regional Commission. So `is_federal` cannot be read off an instrument today by anybody, which is why it has stayed open.
- **No category detail on the billing.** All 10 invoice lines carry one undifferentiated `OTHER` category for 937,073.07, so **nothing on the record says what was billed for.** That is the same shape as Digital Engineering, and it is what makes a cost-to-billing comparison impossible rather than merely hard.
- **No service period on 9 of 9 invoices**, so nothing ties a bill to the months it covers. What the register holds is the invoice date, which is not the same fact.
- **The labour is entirely management reconstruction.** Not one hour on this objective is timesheet-backed, which is the same 200.430(i) exposure the rest of 2025 carries and is worth saying out loud if the answer turns out to be *federal*.

The nine invoices as issued, which is the whole of what the register knows about the billing:

| Invoice | Dated | Total | Billed to |
| --- | --- | ---: | --- |
| 9095 | 31 Jan 2025 | 118,007.31 | Appalachian Regional Commission |
| 9377 | 31 May 2025 | 296,012.98 | Appalachian Regional Commission |
| 9452 | 30 Jun 2025 | 54,018.41 | Appalachian Regional Commission |
| 9453 | 31 Jul 2025 | 63,080.94 | Appalachian Regional Commission |
| 9592 | 31 Aug 2025 | 68,324.15 | Appalachian Regional Commission |
| 9644 | 30 Sep 2025 | 93,602.14 | Appalachian Regional Commission |
| 9705 | 31 Oct 2025 | 72,901.59 | Appalachian Regional Commission |
| 9761 | 30 Nov 2025 | 90,435.77 | Appalachian Regional Commission |
| 9813 | 31 Dec 2025 | 80,689.78 | Appalachian Regional Commission |

The billing is monthly except once: 120 days separate 31 Jan from 31 May. That is a fact about the billing rather than about the work, and with no service period recorded nothing on the record says which months the second one covers.

## 4. Which way the flag moves things

Both directions, because a memo that priced only one of them would be the answer chosen before the question:

| if Rising Tides is… | then |
| --- | --- |
| **not federal** (today's record) | 582,085.53 stays `NOT_APPLICABLE`; nothing reaches the SEFA; the indirect rate does not apply to it and no recovery is available on it |
| **federal** | 582,085.53 becomes federally chargeable and every one of those judgments has to be re-made with a federal treatment; the award reaches the SEFA, which moves the Single Audit scope and the 200.501 threshold; the reconstruction of the labour becomes a 200.430(i) question on a federal charge |

And the 132,803.04 difference between the invoices and the grant income reads differently under each answer — a cut-off question on a commercial contract, and an over-billing question on a federal award. It is declared in the loader with a reason and it has never been settled by anybody.

## 5. What to do, in order

**Nothing below is a step the system can take on its own.** Each one is a judgment or a document somebody has to go and get.

### Before the meeting

1. **Ask YBI for the executed ARC instrument** — the award document itself, not a summary. Four things off its face settle this: the **instrument type** (grant, cooperative agreement, subaward or procurement contract), the **ALN/CFDA number**, the **period of performance**, and the **indirect-cost provision**. The first two answer `is_federal` and the SEFA; the fourth decides whether any of the indirect work applies.
2. **Ask what the ten invoice lines are made of.** One `OTHER` category for the whole year is the record's biggest blind spot on this award. The monthly detail behind the billing is a column their export already has.
3. **Ask Tom which reading his workbook took, and why.** His workbook says federal and the objective master says not; he is the only person who knows which of those was a decision and which was a default.

### Once the instrument is in hand

4. **File it.** `/documents` → upload. The **kind decides where it lands**, so say what it is: `grant-agreement` if ARC awarded it directly, `subrecipient-agreement` if it flows through somebody else, `award-agreement` otherwise. All three file under *awards*; getting it wrong costs a few seconds of browsing and nothing else. The text is read as the file arrives, so a clause can afterwards be checked against the document rather than recalled.
5. **Open the award row — and it takes a developer today.** Nothing in the API creates one; the four on the register came from `scripts/load_awards.py` and a migration. Until a row exists, `PUT /contracts/{award}/terms` answers *No contract* and every constraint test on this objective stays unevaluable.
6. **Then record each provision with the clause it came from** — `/contracts` does have that door. `load_contract_terms.py`'s own rule: *a provision with no citation is somebody's recollection of a contract, which is worth nothing in a dispute and worse than nothing in a file.*
7. **Settle `is_federal` — and that takes a developer too.** See below.
8. **If the answer is federal, the 33 judgments have to be re-made** — unseal with a written reason, reclassify, re-seal, recompute. That supersedes the rate on file, which is the mechanism working rather than breaking: the auditor's ask does not get to move a sealed judgment quietly.

## 6. Two doors that are not there, found writing this

Steps 5 and 7 need a developer, and neither is a thing the controller can do at a screen. Both are the capability-with-no-door shape this repository keeps finding, and they sit on the one path an auditor's question actually takes.

**Nothing creates an `award` row.** Not a route, not a screen. The four on the register came from `scripts/load_awards.py` and migration `004`, and `PUT /contracts/{award}/terms` — which *does* have a door, and which `Contracts.jsx` calls — answers **404 *No contract*** until a row exists. So a new award is a code change and a deploy, and the shape of that was already visible in the four: they are transcriptions of documents, which is why a loader was the right answer *then* and is the wrong answer for an award that arrives next week.

**`cost_objective.is_federal` is write-once with no amendment door.** `POST /api/contracts/charge-codes` sets it when a code is *opened* and answers 409 on one that exists; nothing anywhere updates `cost_objective`. So the single field this entire question turns on cannot be changed through any screen or route.

It is named here rather than fixed on the way past, because *what the door refuses* is the interesting half and it is a judgment somebody has to make. Opening a federal code already demands a CFDA — *without it the award cannot reach the SEFA, and the Single Audit scope is decided by what is on the SEFA.* An amendment that moves an objective **into** federal scope should demand at least the same: the number, a written reason, the document behind it, and a count of the settled judgments it invalidates, printed before anybody presses it. Built carelessly it is a flag somebody flips the day before an audit, which is the one thing this system exists to make impossible.

