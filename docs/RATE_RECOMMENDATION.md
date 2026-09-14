# The 2025 cost build-up, and the rates that fall out of it

**Every figure in this document was computed by the engine against the live
2025 record on 12 September 2026, from an empty database.** Nothing here is
recalled, and nothing is asserted that the engine did not produce. The
scenarios were each run by unsealing, reclassifying through the real API,
re-sealing and re-computing — the same path a controller takes — with the
stored `admin_labour_basis` and every `pool_variance` read back afterwards, so
a scenario that silently did not apply cannot be reported as one that did.

Reproduce it: `scripts/seed.sh`, then `scripts/classification_log.py --apply`,
then seal and `POST /api/rates/compute`.

> **Two of these questions have since been decided, and
> `docs/AMERICA_MAKES_RESTATEMENT.md` carries the answer through to the
> invoices.** General administration goes into the G&A pool across every
> programme (`admin_labour = POOL`), and 5227 portfolio consulting stays in the
> base as contractor cost under 200.331. On the record as it stands — no
> facilities carve-out — that is **21.90% fringe and 43.99% combined**; at the
> provisional 20% tenant share this document recommends, **37.67%**. Everything
> below still reads as written: §4.3 and §4.4 are the two questions that were
> open when it was drafted, and the measurements either way are unchanged.

---

## 1. The short answer

| | | |
| --- | ---: | --- |
| **Fringe** | **21.90%** | on salaries and wages — the payroll register, $1,835,047.17 |
| **Indirect, combined** | **37.67%** | on MTDC — recommended, and the one number here that rests on an assumption |
| | *band 27.06% – 43.01%* | once the two missing documents arrive |
| | *band 9.58% – 50.23%* | today, before they do |

**The fringe rate is not in the band.** It is 21.90% in every scenario below
that does not move an account into the fringe pool, because both of its parts
are anchored to source documents rather than to a judgment: the numerator is
the six accounts the P&L names as fringe ($401,783.60) and the denominator is
the controller's payroll register ($1,835,047.17). Divide them and 0.2190
falls out. Migration `067` holds both anchors; both tie at 0.00.

**The books are finished. The band is not about the books.** 757 of 757 cost
groups are judged, $0.00 unclassified, and every control in the system ties:
all eleven cross-reference points, all four `v_rate_anchor` rows, and
`pool_variance` 0.00 on all four rates under both bases. The width of the band
comes from five named questions, and **two documents close most of it.**

---

## 2. The build-up as computed

Recorded state: 757 judgments, seal
`60fb3f4b52219514d8f0dc8d20c962ad2fd902dee0cf2407da91f2a93d215a37`,
`admin_labour_basis = OBJECTIVE`.

### The pools

| pool | allocable | |
| --- | ---: | --- |
| DIRECT | 2,425,193.27 | cost on a final objective |
| EXCLUDED | 1,906,942.40 | out of the pools and out of the base — the wage accounts, the pass-throughs, the 200.1 exclusions |
| OVERHEAD | 1,497,879.12 | occupancy |
| FRINGE | 401,783.60 | the six accounts on the face of the P&L |
| FUNDRAISING | 281,203.71 | bears indirect, recovers nothing — 200.413 |
| G&A | 263,517.59 | general administration |
| UNALLOWABLE | 115,640.95 | bears indirect, recovers nothing — Appendix IV B.3.d |
| | **6,892,160.64** | signed sum of every live decision line, and `POOLS_ACCOUNT_FOR_JUDGMENTS` ties to it |

Scope classified: **$10,180,642.10 of $10,180,642.10 — 100.0%.** The scope is
absolute dollars over the P&L less the Income section (`v_cost_line`); the
signed position above is the same judgments read the other way, which is why
the two figures differ and neither is wrong.

### The base

| | | |
| --- | ---: | --- |
| Direct salaries and wages | 1,835,047.17 | the payroll register, to the cent |
| Fringe on them, at 21.90% | 401,875.33 | |
| Direct non-labour | 2,822,037.93 | DIRECT + FUNDRAISING + UNALLOWABLE, each on its own objective |
| **MTDC** | **5,058,960.43** | |

### The rates

| | pool | base | rate |
| --- | ---: | ---: | ---: |
| FRINGE | 401,783.60 | 1,835,047.17 | **21.90%** |
| OVERHEAD | 1,497,879.12 | 5,058,960.43 | 29.61% |
| G&A | 263,517.59 | 5,058,960.43 | 5.21% |
| **INDIRECT_COMBINED** | 1,761,396.71 | 5,058,960.43 | **34.82%** |

**This 34.82% is not a proposable rate, and that is the most important
sentence in this document.** It carries **no 2 CFR 200.465 facilities
carve-out**, because no building is on the record and
`v_facility_occupancy` returns nothing — so every dollar of tenant and vacant
occupancy cost sits in the federal pool. It is the ceiling of the band, not
the recommendation.

---

## 3. What is settled, and what is not

The user's read is right: most of it is straightforward. Precisely how much:

| | amount | settled? |
| --- | ---: | --- |
| **Numerator — the indirect pool** | **1,761,396.71** | |
| OVERHEAD other than depreciation | 647,496.23 | pool settled; exposed to the carve-out |
| Depreciation | 850,382.89 | pool settled; **allowability open** (200.436(b)); exposed to the carve-out |
| G&A other than the two below | 185,256.45 | settled |
| Metz Consulting retainer | 73,024.44 | **open** — 200.413(c) |
| 5137 Payroll Processing Fees | 5,236.70 | **open** — fringe or G&A |
| **Denominator — MTDC** | **5,058,960.43** | |
| Salaries and wages | 1,835,047.17 | settled — the register, anchored |
| Fringe on them | 401,875.33 | settled once 21.90% is |
| Direct non-labour other than 5227 | 2,233,499.04 | settled |
| 5227 Portfolio consulting | 588,538.89 | **open** — 200.331 contractor or subrecipient |
| *of the wages above, YBI-GA* | *322,358.32 incl. fringe* | **open** — objective or G&A pool |

**82.0% of the base is settled.** The numerator looks worse than it is:
$185,256.45 of it is untouched by any open question, but the carve-out touches
every dollar of overhead, which is why one missing measurement moves the
answer more than every classification judgment put together.

---

## 4. The five open questions, each measured on its own

Each row is the combined indirect rate with **that one question** moved and
everything else at the recorded baseline. Engine-computed, both bases.

| question | OBJECTIVE | POOL | move |
| --- | ---: | ---: | ---: |
| *baseline* | **34.82%** | **43.99%** | |
| 200.465 carve-out at 10% tenant share | 31.86% | 40.83% | −2.96 |
| 200.465 carve-out at 20% | 28.90% | 37.67% | −5.92 |
| 200.465 carve-out at 30% | 25.93% | 34.51% | −8.89 |
| 200.465 carve-out at 40% | 22.97% | 31.34% | −11.85 |
| 200.465 carve-out at 50% | 20.01% | 28.18% | −14.81 |
| Depreciation wholly unallowable (200.436(b)) | 15.42% | 22.08% | −19.40 |
| 5227 out of the base (200.331 subrecipient) | 39.40% | 50.23% | +4.58 |
| Metz retainer wholly direct (200.413(c)) | 32.90% | 41.81% | −1.92 |
| 5137 into the fringe pool | 34.68% | 43.86% | −0.14 |

The carve-out is **exactly linear** in the tenant share — the engine takes
`share × the OVERHEAD pool` — which is why five runs draw the whole line and
Kelly's measurement can be substituted straight into it.

### 4.1 The facilities carve-out — the largest, and one form from being closed

2 CFR 200.465 requires the rental operation's share of occupancy cost to leave
the federal pool. The share is square footage, YBI has **no building on the
record at all**, and nothing distinguishes *there is no tenant space* from
*nobody has measured any*. The space book already went out through
`/requests`, pre-filled from YBI's own lease schedule; the one column it asks
for is square footage.

What is known and bounds it: **26 tenancies across five buildings, $601,269.48
of contracted annual rent** on the 2025 lease schedule — Steelite International
$286,608.48, Tech Block 5 $145,516.92, NCDMM America Makes $108,000.00, 255 W.
Federal $61,144.08. An organisation collecting $601,269 of rent has a rental
operation, and its share of occupancy cost is not zero.

**And the engine's carve-out double-counts what tenants already reimburse.**
$100,931.51 of named-tenant credits are already booked into the OVERHEAD
accounts — Steelite for property tax and Semple utilities, NCDMM for Boardman
electric and gas, Ursa Major, Vista AST, Tailored Alloys, AMI, Factset. The
engine computes `share × the pool net of those credits`, which removes the same
money twice, by `$100,931.51 × (1 − share)`:

| share | over-carved | worth |
| ---: | ---: | ---: |
| 10% | 90,838.36 | 1.80 pts |
| 20% | 80,745.21 | 1.60 pts |
| 30% | 70,652.06 | 1.40 pts |
| 40% | 60,558.91 | 1.20 pts |

It errs **against YBI**, so it is not urgent, but it is wrong: the correct
computation is `share × gross occupancy cost, less what tenants have already
paid`. It is left as a recommendation rather than changed here, because which
credits are tenant recovery is a judgment on the controller's side of the
line. Of $133,998.11 of credits in the pool, $100,931.51 name a party and
$33,066.60 do not — and two of that remainder are plainly not tenant recovery
at all ($22,967.24 marked *to reclass into correct account* and $10,099.36 of
insurance proceeds for parking-lot column damage), which is why the figure
above is the named-party one.

A second thing to decide with it: the engine applies the square-footage share
to the **whole** OVERHEAD pool, including $86,887.30 of T1 access, $18,612.87
of telephone, $57,596.36 of insurance and $18,179.62 of equipment — $181,276.15
that square footage does not drive.

### 4.2 Depreciation and 200.436(b) — the largest that no document on file can settle

$850,382.89, in OVERHEAD, federal treatment `PENDING`. Depreciation on a
federally funded asset is unallowable, and **the fixed-asset schedule has no
funding-source column** — which 2 CFR 200.313(d)(1) requires, and which is a
finding in its own right. YBI's buildings were funded in part by the EDA
CD-450 award, so the answer is neither nought nor all of it.

The register went out through `/requests` pre-filled with all 263 assets; the
one column it asks for is funding source. Until it comes back, `PENDING` is the
honest treatment: the cost is where it belongs and the claim is open.

### 4.3 Administrative labour — a judgment the certifications are about to settle

`YBI-GA` carries $264,444.89 of wages, $322,358.32 with fringe. Treated as a
**cost objective** it takes an allocation of indirect; treated as **pool** cost
it forms part of G&A, which is where 2 CFR 200 Appendix IV B puts the
director's office, accounting and personnel administration. It is worth
**8.77 points at a fixed carve-out** and 9.17 points with none.

The evidence found this run, from the hours log:

| | YBI-GA hours | of total | other objectives |
| --- | ---: | ---: | ---: |
| Jaric | 941.5 | 45.1% | 6 |
| Ewing (the administrator) | 282.9 | 13.5% | 8 |
| Sprowl | 155.4 | 7.4% | 8 |

Every one of the ten people carrying YBI-GA wages splits their time; nobody is
100% on it, and the three with a monthly log book it as *one line among seven
to nine*, beside named programmes. **That is a real assignment, not the bucket
unattributable time went into** — which is the counter-argument this decision
turns on, and it does not survive the log.

The caveat is size: those three are $66,730.60 of the $264,444.89. The other
seven have a single summary row and no hours evidence at all. **The
certification exercise now under way is exactly what settles it** — when those
seven read and sign their reconstructed sheets, the YBI-GA hours on them are
either affirmed or corrected, and the question closes on evidence rather than
on argument.

### 4.4 Portfolio consulting and 200.331 — worth 4.58 points

`5227 Portfolio consulting`, $588,538.89 net over 442 lines and 72 payees: YBI
pays a service provider for a portfolio company and books half back. A
*contractor* provides services inside the recipient's own programme and counts
in MTDC in full; a *subrecipient* carries out part of a federal programme in
its own right and counts only to the first $25,000. These consultants deliver
into YBI's incubation programme against YBI's scope, which makes them
contractors — and that is also the treatment that recovers, because the
selection, scoping and administration of those engagements is precisely what
the G&A pool pays for.

Reading them the other way takes the base *down* and the rate **up**, to
39.40% / 50.23%. That is the direction worth knowing: the conservative reading
of the classification is the aggressive reading of the rate.

### 4.5 The two small ones

**The Metz Consulting retainer**, $73,024.44 in G&A. His hours log puts 35.47%
of his effort on ESP, Hybrid II and Rising Tides — $25,899.83 — and YBI already
direct-charges his project work when it is billed as project work ($4,880.00 on
ESP). Moving the effort share takes the combined rate from 34.82% to 34.13%;
moving the whole group takes it to 32.90%. It stays in G&A because 200.413(c)
takes four conditions and the third — explicitly budgeted, or prior written
approval — is exactly what these awards do not have.

**`5137 Payroll Processing Fees`**, $5,236.70. Arguably the cost of
administering the payroll the fringe pool pays for. Worth 0.28 points of fringe
(21.90% → 22.18%) and 0.14 points of combined, in opposite directions. It stays
in G&A because the six fringe accounts are a transcription of a judgment
somebody made once, and inventing a rule to derive that judgment would be
guessing at it.

---

## 5. Min, mid, max

### Max — 50.23%

`POOL` basis, 5227 outside the base, no carve-out, depreciation fully
allowable. Every open question resolved in favour of recovery. Engine-computed.

**Do not propose this.** It contains no 200.465 carve-out, and a rate proposed
without the one adjustment the regulation requires will not survive the first
question a reviewer asks.

### Mid — 37.67% combined, 21.90% fringe · **recommended**

`POOL` basis with a **provisional 20% tenant share**. Everything else at the
recorded baseline: 5227 in the base as contractor cost, the Metz retainer and
5137 in G&A, depreciation in OVERHEAD at `PENDING`.

| | |
| --- | ---: |
| FRINGE, on salaries and wages | **21.90%** |
| OVERHEAD, on MTDC | 25.30% |
| G&A, on MTDC | 12.37% |
| **INDIRECT_COMBINED, on MTDC** | **37.67%** |

**The 20% is the only assumed number in this document**, and it is flagged
rather than buried: substitute Kelly's measurement into §4's linear table and
the rate follows. On the OBJECTIVE basis the same 20% gives **28.90%**.

### Min — 9.58%

`OBJECTIVE` basis, 40% carve-out, depreciation wholly unallowable, the whole
Metz retainer direct, 5137 in fringe, 5227 in the base. Engine-computed.

This is a **floor, not a forecast**: it resolves every open question against
recovery at the same time, including two — a 40% tenant share and 100%
federally funded depreciation — that are each individually plausible and are
unlikely to both be true. It is here because it answers one question worth
answering: **below about 10%, YBI is better off on the de minimis rate it is
already using**, and that is the point at which this whole exercise stops
paying for itself. Nothing in the evidence puts the answer there, but the
controller should know where the floor is.

### The band, before and after the two documents

| | OBJECTIVE | POOL |
| --- | ---: | ---: |
| today — square footage and funding source both unknown | 9.58% – 39.40% | 15.83% – 50.23% |
| with both known (illustrated at 20% and 0% funded) | 27.06% – 32.70% | 35.58% – 43.01% |

**Two spreadsheets are worth roughly 24 points of width.** Both are already
requested, both are pre-filled from YBI's own documents, and each asks for a
single column.

---

## 6. What it is worth

On the cost YBI actually incurred against the four America Makes objectives in
2025 — $999,842.96 of MTDC across Drive AM, LTM, Digital Engineering, Hybrid II
and AM-Other:

| | supported indirect |
| --- | ---: |
| budgeted across all four Schedule Bs | 109,272.76 |
| at the 10% de minimis they were billed under | 99,984.30 |
| at 28.90% (OBJECTIVE, 20% carve-out) | 288,954.62 |
| **at 37.67% (recommended)** | **376,640.84** |
| at 34.82% (as computed, no carve-out) | 348,145.32 |

Against **$109,272.76 budgeted**, of which Drive AM budgets nothing at all on
$583,594 of labour and Hybrid nothing on $449,043. The document YBI issued is
itself the record of what it was never budgeted to claim.

On the three invoices actually on file — $57,961.42 of billing — the
restatement at 34.82% is **$16,137.57** (Drive AM $13,090.20, LTM $2,568.94,
Hybrid II $478.43), each recorded as `PROPOSED` and each needing a §4.4 written
modification before it becomes a claim. That figure is small because almost
none of the 2025 cost was ever invoiced; the forward number above is the case.

---

## 7. Two things this run found in the code

**A rate computed under a policy nobody chose.** `POST /api/rates/compute`
takes `admin_labour`; the column it is stored in is `admin_labour_basis`.
Sending the column name — which is the name anybody reads off the schema —
made pydantic drop the key, apply the `OBJECTIVE` default, compute, persist and
answer **200**. Nine points of combined rate, chosen by a typo, with nothing
saying so. `ComputeIn` now refuses a key it does not know: it is the one body
in this API that does, because every field on it is a policy with a default,
and the house rule of accepting a field you no longer use is the wrong trade
for a rate. `tests/test_compute_policies.py` holds it, and it also caught
`scripts/review_system.py` sending `period` in the body, where it is a query
parameter and did nothing.

**The carve-out double-counts booked tenant recovery** — §4.1 above.
Recommendation, not a change: it is a modelling judgment, and it errs against
YBI.

---

## 8. What to do next, in order of what it is worth

1. **Get the square footage.** ~24 points of band, one column, already asked
   for. Nothing else on this list comes close.
2. **Get the funding source on the asset register.** 200.313(d)(1) requires
   the column to exist regardless; until it does, $850,382.89 of the pool
   cannot be claimed with confidence.
3. **Finish the certifications.** 43 people, zero signed. This does not move a
   figure — adopting the reconstruction reproduces its shares exactly — but
   200.430(i) goes to the allowability of the *entire* direct labour charge,
   and it is what settles §4.3 on evidence.
4. **Decide the administrative labour basis**, with the certifications in
   hand. 8.77 points.
5. **Fix the carve-out arithmetic** before the square footage arrives, so the
   first real measurement produces the right answer rather than one 1.6 points
   low.
6. **Confirm 200.331 on the portfolio consultants.** 4.58 points, and the
   answer that recovers is also the one the facts support.

Items 5 and 6 are ours. Items 1 to 4 are YBI's, and three of the four are
already in motion.
