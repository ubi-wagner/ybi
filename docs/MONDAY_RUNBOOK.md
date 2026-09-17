# Monday — the run sheet

*Generated from the record by `scripts/runbook.py`, which will not write over a failing crosscheck. Every figure below was read by `scripts/drive_invoice_ties.py`; none was typed beside it.*

*17 September 2026*

**Read §0 first.** The record is at the end of the path this document used to describe, so every step is **verification, not construction**. Following an earlier version literally would have had the controller press *Seal* on a sealed set.

```bash
DATABASE_URL=... ./scripts/readiness.py           # read-only
DATABASE_URL=... python3 scripts/drive_invoice_ties.py   # the crosscheck
YBI_SEED_PASSWORD=... ./scripts/monday.sh --full  # the sandbox test
```

**Illustrated:** `docs/MONDAY_GUIDEBOOK.pdf` photographs every screen below. **Recommendations to tick:** `docs/MONDAY_ANCHOR.pdf`.

---

## 0 · Where the record stands

| | | |
| --- | --- | --- |
| the eleven control points | **11 of 11 tie** | a rate is refused while any is open |
| the classification | **757 of 757 groups**, 100.0% | 0.00 unclassified |
| the seal | **Tom Metzinger**, 12 Sep 2026 22:50 UTC | covering 757 live judgments |
| the rate | FRINGE **21.90%** · INDIRECT_COMBINED **22.48%** | administrative labour on the **POOL** basis |
| the rate anchors | **4 of 4 tie** | 4 of 4 pools at variance 0.00 |
| the invoice register | **61 invoices**, 2,964,077.32 | all of 2025, reconciled to the ledger |

**So Monday is a review, not a build.**

## 0.1 · The crosscheck this sheet was generated from

The register against the ledger's own grant income — two records of the same billing, neither derived from the other.

| award | invoices | billed | ledger | difference | |
| --- | ---: | ---: | ---: | ---: | --- |
| DRIVE-AM | 12 | 579,240.87 | 579,240.87 | — | to the cent |
| LTM | 12 | 368,222.24 | 368,222.24 | — | to the cent |
| DIG-ENG | 7 | 579,074.25 | 579,074.25 | — | to the cent |
| HYBRID-II | 9 | 187,416.05 | 191,638.05 | 4,222.00 | Oct-Dec on the ledger with no invoice — the tail after billing stopped |
| AAMEN | — | 313,050.84 | 313,050.84 | — | to the cent |
| RISING-TIDES | — | 937,073.07 | 804,270.03 | -132,803.04 | 86,281.30 is the 2024 portion, named on the January invoice; the rest is accrual timing across Jan-May |

And the billed non-labour against the cost the ledger carries:

| award | billed | ledger | | |
| --- | ---: | ---: | ---: | --- |
| DRIVE-AM | 274,757.07 | 181,880.88 | -92,876.19 | billed in ODCs above the cost classified to Drive AM. Either the classification under-attributes or the billing over-claimed, and it is the open question under the largest credit in the restatement |
| LTM | 233,900.00 | 266,384.07 | 32,484.07 | cost incurred and never billed — including a 19,500.00 'UNI Q3-Q4 2025' line with no payee. Unbilled cost, which runs in YBI's favour |
| DIG-ENG | — | — | **not evaluable** | its invoices carry a single undifferentiated monthly line, so the billing does not separate labour from non-labour |
| HYBRID-II | 15,000.10 | 15,000.10 | ties | to the cent |

**Not evaluable, and why** — a control that cannot be evaluated has not passed, and it has not failed either:

- DIG-ENG       NOT EVALUABLE — its invoices carry a single undifferentiated monthly line, so the billing does not separate labour from non-labour
- 12 invoice(s) on AAMEN carry no award — the schema allows it, and an award register that has not caught up is not a reason to hold evidence out
- 9 invoice(s) on RISING-TIDES carry no award — the schema allows it, and an award register that has not caught up is not a reason to hold evidence out

---

## 1 · Confirm the books still agree — Tom

`/reconcile`. **11 of 11 tie today.** This step is to confirm they still do. `POST /api/rates/compute` returns 409 while any one is open.

A difference is closed by *naming* the lines behind it, never by netting it. The Bacon $45,053.23 donor credit is the change most likely to have happened over the weekend — when it is reposted in QuickBooks the reconciling item comes off with it, or the correction counts twice.

## 2 · Review what stands — the controller team

`/classify`. **This is the work.** 757 judgments were recorded through the API under Tom's name, each with a written rationale in `docs/CLASSIFICATION_LOG.md`. What has *not* happened is a person reading them and affirming they stand.

If every judgment stands, nothing is required: the seal is current and so is the rate. **Skip to §5.** If any is wrong, go to §C.

## 3 · The seal — already held, and only Tom may move it

Sealed 12 September 2026 by Tom Metzinger, covering 757 live judgments. **Nothing to do unless something changes.**

## 4 · The rate — already computed, on the basis that was chosen

| | | |
| --- | ---: | --- |
| FRINGE | **21.90%** | pool 401,783.60 over 1,835,047.17 SALARIES_WAGES |
| OVERHEAD | **10.11%** | pool 479,021.14 over 4,736,602.11 MTDC |
| G&A | **12.37%** | pool 585,875.91 over 4,736,602.11 MTDC |
| INDIRECT_COMBINED | **22.48%** | pool 1,064,897.05 over 4,736,602.11 MTDC |

**If you recompute for any reason, choose POOL again.** The screen defaults to `OBJECTIVE`, which is worth about nine points of combined rate on the same sealed judgments.

## 5 · Check the stack — Tom

`/review/rate`. **4 of 4 pools** at `pool_variance` 0.00 and **4 of 4 rate anchors** tying. Nothing on that screen is computed — every figure is read from the row it was recorded in.

---

## 7 · The paper, at any time — Tom or the auditor

Nothing downstream is blocked by a missing signature or a missing document. A workbook, a reissued invoice, the amendment memorandum and the acceptance form can all be produced today; what changes is what the paper *says* about itself.

- **On a screen.** `/reports` and `/review` for the workbooks; `/restate`, open a proposal, **The papers that go with it** for the memorandum and the acceptance form. Every one of those screens carries the certification band at the top, in whichever direction is true.
- **The whole set at once.** `YBI_SEED_PASSWORD=... python3 scripts/publish.py` writes every workbook, every reissued invoice and both papers per award into `docs/publications/`, with a manifest and a README rendered from it. It fetches each document from the route the screen calls, so a figure in the set and the same figure on the screen cannot disagree, and it **writes nothing to the cost record**.

The acceptance form prints two readings and they are not meant to add up: *as billed, line by line* is each invoice's indirect against what the rate supports on its own base, and **THE POSITION** is the objective rebuilt against the cost record. The position is the only figure the form asks a sponsor to accept.

---

## C · If something has to change

1. **Unseal** — `/rates`, with a written reason. It supersedes every rate computed against that seal.
2. **Correct the judgment** — `/classify`. Reclassifying supersedes rather than edits; the prior judgment stays on the record.
3. **Re-seal** over the corrected set.
4. **Recompute** — and choose **POOL** again (§4).
5. **Re-check** — §5, then re-run the crosscheck and regenerate this sheet: `python3 scripts/runbook.py --write`.
6. **Tell whoever quoted the old figure.**

*Correct by superseding, never by editing.*

## P · Running in parallel, and none of it blocks the above

- **The 43 timesheets.** 0 of 43 certified, and **0 employment terms are on the record**, so no draft can be built for anybody. Two gates, and both come out of the roster reply — which also carries the addresses the accounts are opened against. Opening them is a second act and it is the administrator's.
- **The square footage.** 5 facilities carry measured space. It is the largest open item and **it gates no classification** — occupancy is OVERHEAD in the 2025 chart and the tenant share comes out at rate time.
- **The funding source on each asset.** 0 of 263 assets name **no** funding source, against 23,419,573.64 of gross cost. 2 CFR 200.313(d)(1) requires the column and the schedule does not carry it, so it is the one thing here that no amount of reading the books can settle. It gates no classification either — depreciation is OVERHEAD whatever the answer — but 200.436(b) cannot be answered until it lands, so the federal treatment on it stays PENDING.
- **Barb's decisions.** `docs/BARB_ONE_PAGE_AM.pdf`.

## What must not be automated, and why

| | |
| --- | --- |
| **The seal** | It is the assertion the rate was not reverse-engineered. A script that sealed would put the machine's name on it. |
| **A certification** | 200.430(i) wants the person whose effort it was. |
| **Adopting a draft** | Theirs to accept or decline. |
| **A reconciling item** | A difference is closed by naming the lines behind it. |
| **Anything sent to a sponsor** | A position YBI takes, in writing. |

---

*Crosscheck: 0 findings, 3 not evaluable. This sheet is not written while any finding stands.*
