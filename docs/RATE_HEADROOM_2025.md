# Where the indirect rate has room, and where it does not

**Regenerate with `python scripts/rate_headroom.py --write`.** Nothing here is written to the record. The certified rate is 24.71%; the structure this measures against is the built one in `docs/DEFENSIBLE_RATE_2025.md`.

It reads **Heidi's measured estate** — 113,235 usable square feet across the buildings on the floor plan of 15 September 2026, which is filed as evidence and **has not been accepted into `space_unit` on the reference record**, because accepting it supersedes a certified rate and that is Tom's act. Run it against a record where that estate is loaded, or every figure below is about a different building.

---

## 1. Why it reads low, and how much of that is structural

| | |
| --- | ---: |
| overhead — the facilities component | **7.58%** |
| G&A — the administration component | **12.37%** |
| combined, of MTDC | **19.95%** |
| fringe, of salaries and wages | 21.90% |

Two facts account for most of the distance to a peer figure, and neither is a cost somebody forgot to collect.

**The estate is mostly somebody else's.** 86.27% of the 113,235 measured square feet is let, committed or vacant, so that share of $1,450,601.08 of occupancy cost never enters the federal pool at all. A university's Facilities component keeps the occupancy YBI has to give up under 200.465. **This is the largest single reason the overhead component is small, and it is the right answer.**

**The base is the whole organisation, not one activity.** MTDC is $4,736,602.11 and the federal share of it is **$1,154,545.23, 24.4%**. A university's F&A rate is computed over organized research MTDC alone; this pool is spread over 11 non-federal objectives as well, which is correct — every activity bears indirect — and it is why one pool over this base produces a small number.

Appendix IV B.2 permits **separate rates by function or location** where activities benefit differently. That is the one structural change that could raise the federal rate without finding a dollar of new cost, and it is not free: it needs evidence that federal work draws administration disproportionately, which this record does not yet carry. It is named here as the largest unexplored option, not as a recommendation.

---

## 2. Every leg, alone, in points of combined rate

Each row moves one judgment and holds the rest at the reference. They interact, so they do not add; §3 runs the two packages.

| leg | reading | combined | Δ pts |
| --- | --- | ---: | ---: |
| Client space | incubator client companies are programme space, their rent credited under 200.406 | 22.67% | +2.72 |
| Client space | the same, **without** crediting the rent — shown to price the credit, not to propose it | 26.70% | +6.75 |
| Client space | America Makes counted as programme too, rent credited | 23.40% | +3.45 |
| Common area | all common is the incubator's own | 26.05% | +6.11 |
| Common area | all common follows the tenants | 17.83% | -2.12 |
| 200.331 | the 6 federal parties over the cap are subrecipients — $313,605.35 leaves MTDC | 21.36% | +1.41 |
| 200.331 | and the 18 portfolio consultants over the cap as well — a further $420,124.00 | 23.61% | +3.66 |
| Segregation | the letting bears its share of G&A, as Appendix IV B.2.a requires of an activity | 17.59% | -2.36 |

**The last row is the one nobody has looked at, and it runs against YBI.** The same argument that keeps let occupancy out of the federal overhead pool makes the letting an *activity*, and an activity bears general administration. `cost_objective` has carried a `RENTAL` row since the master was built and **nothing is classified to it, nothing is allocated to it and no labour sits on it** — the dead-register shape, in the one place it costs rather than pays.

## 2a. The tenancy roster the client-space leg turns on

Matched on the occupant the floor plan names, which is a **starting list and not the answer**. Some of these are plainly not incubator clients — a maintenance contractor, a charity, an appraiser — and the test is the tenancy agreement, not the suite number. A wrong row here moves the rate, so it is printed rather than summarised.

| occupant | sq ft | rent | this run treated it as |
| --- | ---: | ---: | --- |
| Steelite | 29,439 | 203,115.96 | let — commercial |
| Steelite 1st Fl & LL | 14,142 | 49,527.00 | let — commercial |
| NCDMM America Makes | 14,092 | 126,720.00 | let — America Makes, the arguable middle case |
| Juggerbot 3D | 8,463 | 62,226.96 | **programme** |
| BDI | 3,542 | 19,491.00 | **programme** |
| Ursa Major | 2,430 | 7,209.96 | **programme** |
| Vista AST | 2,196 | 20,682.00 | **programme** |
| Fitz Custom QOZB | 2,000 | 27,996.00 | **programme** |
| Tailored Alloys | 1,692 | 8,352.00 | **programme** |
| Beloved Guardians | 1,115 | 4,689.96 | **programme** |
| American Maintenance | 957 | 7,659.96 | **programme** |
| MVMC - | 953 | 3,000.00 | **programme** |
| Ralph Zerbonia | 826 | 1,455.00 | **programme** |
| Made by Morgan LLC | 589 | 3,534.00 | **programme** |
| NeuroReef | 556 | 3,333.60 | **programme** |
| Azanna Elise, LLC | 508 | 3,048.00 | **programme** |
| Autism Society | 476 | 2,850.00 | **programme** |
| Parallax | 460 | 4,320.00 | **programme** |
| Marquee - | 412 | 2,475.00 | **programme** |
| M. Jones LLC | 382 | 2,292.00 | **programme** |
| Bplanet - Atrl8 | 343 | 2,232.00 | **programme** |
| JSO Technologies | 291 | 1,746.00 | **programme** |
| Greg Babinack | 155 | 1,237.56 | **programme** |
| Equipment Appraisal Services | 118 | 960.00 | **programme** |

---

## 3. The two packages

| | overhead | G&A | combined | loaded on labour |
| --- | ---: | ---: | ---: | ---: |
| reference — `DEFENSIBLE_RATE_2025.md` | 7.58% | 12.37% | **19.95%** | 1.4622× |
| **defensible**: client space in, rent credited, the letting bears G&A | 10.30% | 10.66% | **20.96%** | 1.4745× |
| stretch: + America Makes, + all common ours, + 200.331 on the federal six | 15.53% | 12.16% | **27.69%** | 1.5566× |

**The defensible package is the recommendation to test, not to adopt.** Every part of it is a judgment somebody at YBI has to make and sign: which occupants are client companies in residence and which are commercial lettings is Heidi's and Tom's answer off the tenancy agreements, not an inference from a suite number.

---

## 4. What has no room, and why saying so is the point

| | |
| --- | --- |
| **Fringe, 21.90%** | Anchored at both ends to source documents — the P&L's six benefit accounts over the payroll register. No floor plan, no determination and no reading of an agreement touches it. |
| **Leave** | 200.431(b) makes paid leave a fringe cost and YBI pays it through the wage accounts as regular compensation, so it is already inside the denominator. Adding it to the numerator would count it twice. |
| **The certified 24.71%** | Not a leg in either direction. It is the same cost with the pool carved back rather than built, and on the measured estate its carve-out exceeds its own pool. |
| **The de minimis floor** | Raised from 10% to 15% by the 2024 revision, for awards issued **on or after 1 October 2024**. All four America Makes awards start before that date — Last Tactical Mile by nine days — so the 10% figure in each agreement is the one that governs unless a modification reissued it. Worth confirming against each subaward instrument rather than the prime's period. |

---

## 5. The rule this list is written under

Classifications are sealed before any rate is computed so that a reviewer can be told the rate was not reverse-engineered. A list of only the readings that raise the number would undo that, whatever the seal says. So three of the eight legs above run **against** YBI and are on the page at the same size as the rest, and the two largest movements in the whole file — the measured estate and the administrative labour basis — are already taken.

The honest summary is short: **the rate is low because YBI is a landlord to a largely non-federal tenancy and spends a quarter of its base on federal work.** The room that exists is in whether the incubator's client companies are tenants or programme, and that is a question about tenancy agreements rather than about accounting.
