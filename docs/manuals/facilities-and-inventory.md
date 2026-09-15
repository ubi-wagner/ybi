# Facilities and inventory

*For whoever holds `FACILITIES` and `INVENTORY`. At YBI that is Heidi.*

Two of the largest numbers in the 2025 indirect rate are yours, and until
this year neither of them could be computed at all.

| what you answer | what it moves | what it was before you answered |
| --- | --- | --- |
| the square footage of each building, and what each part is used for | the 2 CFR 200.465 facilities carve-out | nothing was carved out; **every dollar of tenant and vacant occupancy cost sat in the federal pool** |
| which assets federal money paid for | 2 CFR 200.436(b) — depreciation on a federally funded asset is unallowable | nothing was excluded, on $850,383 of depreciation |

Measured on the live 2025 record, those two answers took the combined
indirect rate from **43.99% to 24.71%**. That is not a rounding. It is the
difference between a rate an auditor can defend and one they cannot, and it
runs *against* YBI — a lower rate means less recovery. That is the honest
direction to err while the measurement is an estimate.

---

## 1. The buildings

**`/classify/space`.** One row per building, then one row per part of it.

You do not write these rows directly. You **propose** them and Tom accepts —
because the rate he signs rests on them, and a measurement that arrives
without him seeing it is a figure on his signature that he never read. The
screen does that for you: fill the form, press Recommend, and it appears on
his list.

### What a building needs

| field | what it means | where to get it |
| --- | --- | --- |
| **Name and code** | what YBI calls it | the lease book already names six: `ybi`, `TBB5`, `Semple`, `Taft`, `AM` |
| **Address** | the street address | three are on documents already: 241 W Federal (YBI Main), 252 W Boardman (TBB5, from the JobsOhio agreement), 255 W Federal (Taft) |
| **Usable square feet** | the floor area that can be occupied — **not** the gross building area | a floor plan, a survey, an appraisal, or the leases if they state areas |
| **Owned** | YBI owns it, or leases it in | the ledger carries no building rent expense for 2025, so on the record YBI owns all five |

**Usable, not gross.** Usable area excludes the lift shafts, stairwells,
plant rooms and structural walls. If the only number you can find is gross,
say so in the note — a stated gross is better than a guessed usable, and it
can be corrected once.

### What each part of a building needs

A building is divided into **space units** and they have to add up to the
building. If they do not, `SPACE_UNATTRIBUTED` fires and the carve-out
refuses to run on that building at all — which puts all of its occupancy cost
back in the federal pool.

| use | what it is | does it come out of the federal pool? |
| --- | --- | --- |
| `TENANT` | let to somebody | **yes** |
| `VACANT` | lettable and not let | **yes** |
| `COMMITTED` | let from a date that has not arrived | **yes** |
| `PROGRAM` | YBI's own programme delivery — names the cost objective it serves | no |
| `ADMINISTRATIVE` | YBI's own offices | no |
| `SHARED_LAB` | the additive-manufacturing laboratory and shared equipment floor | no |
| `COMMON` | corridors, lobbies, lavatories | rides along proportionally |

**Vacant space is the one people forget, and it is worth money.** Space that
is available to let and not let is the rental operation's cost, not the
federal awards'. If half a floor stood empty for the year, say so; it takes
cost *out* of the federal pool.

`months_occupied` is for a unit that was let for part of the year. Twelve
means the whole year. If a tenant left in May, that is 5.

### Where the estimate on the record came from

There is no measurement on file, so the record currently carries an
**estimate**, marked `TEST_ASSUMPTION`, with its derivation in the note of
every row:

* the estate is the 2024 audited statements' $21,098,684 of land, building
  and improvements, less $107,530 of land, at **$116.27 a square foot** — the
  rate the JobsOhio Grant Agreement states for this estate ($2,092,861 of
  building fixed asset investment for approximately 18,000 square feet);
* let space is the 2025 rent roll at **$7.00 a square foot**, which is the
  rate at which the rent roll accounts for 50.5% of that estate — the floor
  of the audited statements' *"predominately available to businesses in
  Mahoning Valley as operating leases"*;
* the balance is split between buildings by capitalised cost.

That gives **180,538 square feet, of which 91,225 (50.5%) is let.** Your
tape measure replaces all of it. Two things to know before you start:

* **No vacancy is claimed**, because nothing on the record measures any. That
  is the one place the estimate is *not* conservative: any vacancy you record
  makes the carve-out larger and the federal rate lower.
* **The shares are what matter, not the areas.** If every building is 10%
  bigger than the estimate, the rate does not move at all. Get the *split*
  right first.

---

## 2. The asset register

**`/classify/assets`.** 263 assets, $23.4m of cost, and one column the
schedule does not carry: **who paid for it.** 2 CFR 200.313(d)(1) requires
that column and its absence is a finding in its own right.

For each asset, one or more funding rows:

| field | what it means |
| --- | --- |
| **Kind** | `FEDERAL`, `STATE`, `LOCAL`, `PRIVATE`, `DEBT` or `UNRESTRICTED` |
| **Amount** | how much of the asset's cost that source paid. It may be part of the cost; the rest is another row, or unanswered |
| **Award reference** | the award number — `EDA 06-79-06300`, `ARC PW-20599` |
| **Funder** | the agency or the donor |
| **Note** | the document you read it off |

**`FEDERAL` is the one that costs money.** Depreciation on the federally
funded share of an asset is unallowable under 200.436(b), so it is excluded
from the overhead pool. Everything else is neutral for the rate.

**A blank is not a zero.** *There is no federal money in this asset* and
*nobody has looked* are different facts and the screen keeps them apart.
Leave it unanswered rather than guessing.

### What is answered now, and the three that need you

The record carries an answer on all 263, on rules stated in each row's note:

| rule | assets | basis |
| --- | --- | --- |
| named federal | 3 | a document names the award against that asset |
| covered federal | 16 | placed in service in 2023 or 2024, when the SEFAs show $465,426 and $2,621,962 of federal capital expenditure against $53,007 and $2,676,739 of additions |
| unrestricted | 244 | placed in service before 2023 or after 2024, when no federal capital award was open |

**Three things to settle, in the order they are worth:**

1. **The EDA share of TBB5 Phase-2.** The closeout letter of 17 November 2025
   puts the final accepted project cost at $2,376,344 and EDA's share at
   $1,903,179 — **80.09%**. The record carries it at 100% federal, which is
   conservative. If the other 19.91% is YBI's own money, $23,777.92 of
   depreciation becomes allowable.
2. **ARC PW-20599-IM-22 and -IM-24.** $1,215,338 of federal expenditure
   across 2023 and 2024, and only $120,310 of it is named against an asset
   (*Xjet ARC Equipment*). Which assets did the rest buy?
3. **The 2024 additions.** Sixteen assets are recorded federal on an
   *aggregate* argument — the year's additions against the year's federal
   expenditure — not on an invoice. Any one of them you can tie to a specific
   award, or rule out, replaces an inference with a fact.

### While you are in there: the equipment

Two columns on the same screen nobody has ever written:

* **`access`** — every asset reads `INTERNAL` because that is the column's
  default and nothing has set it. `FREE`, `SUBSIDIZED` and `CHARGED` are what
  `v_equipment_subsidy` counts, so until somebody says which machines go out
  on loan and on what terms, the in-kind contribution YBI makes to its
  portfolio companies reports as zero.
* **`footprint_sqft`** — what a machine stands on, which is how equipment
  space is attributed to a building.

Neither moves the rate. Both are on the 990 narrative and in the board pack.

---

## 3. What happens after you press Recommend

1. It goes on Tom's list at `/classify/review`, a building above the rooms
   inside it, because a room cannot be written before its building exists.
2. He accepts, and the row is written **through the same route the screen
   uses** — so every rule that would have refused your typing refuses his
   accepting.
3. `/audit` — the walk — moves. SPACE and ASSETS go from `NO DATA` to `OPEN`
   to `DONE`.
4. Tom recomputes and the rate moves.

**You cannot accept your own recommendation**, even though you hold
`CONTROLLER` as well. That rule is in the database, not the screen: the point
of the loop is that two people looked.

## 4. Two things that are not your job

* **Valuing your own donated time.** Nobody values their own — 2 CFR
  200.306(e) is exactly about that, and the table refuses it.
* **Deciding which pool occupancy cost goes in.** That is the
  classification queue. You divide the space; the carve-out does the rest.
