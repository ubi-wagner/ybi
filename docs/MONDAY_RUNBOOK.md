# Monday — the run sheet

**Read §0 first.** The first version of this document described building the
year from nothing, and the record is already at the end of that path — every
step below is **verification, not construction**. Following the old version
literally would have had the controller press *Seal* on a sealed set and
recompute a rate that is already current.

Pre-flight, the night before or first thing:

```bash
DATABASE_URL=... ./scripts/readiness.py              # read-only, writes nothing
DATABASE_URL=... ./scripts/monday.sh                 # read-only checks
YBI_SEED_PASSWORD=... ./scripts/monday.sh --full     # and the sandbox test
```

**Illustrated:** `docs/MONDAY_GUIDEBOOK.html` photographs every screen below,
driven by `scripts/walk_runbook.py`. It walks a sandbox **from empty**, so it
shows what each screen looks like and what each step *means* — the record you
will open on Monday is further along, per §0.

**In hand while you work:** `docs/MONDAY_ANCHOR.pdf` — every current
recommendation from every document in `docs/`, dealt into the sequence below,
with the screen each one is visible on and a tick box. Nine documents carry
these and none of them is ordered the way the work is done, so a
recommendation nobody can find at the moment it applies is one nobody checks.
Its figures are read from the live record by `scripts/monday_anchor.py` rather
than recalled; regenerate it if the record moves.

---

## 0 · Where the record actually stands

Read from the live record, 13 September 2026. Re-read it any time with
`scripts/readiness.py`, which writes nothing.

| | | |
| --- | --- | --- |
| the eleven control points | **11 tie**, 0 open, 0 unevaluable | 6 reconciling items recorded |
| the classification | **757 of 757 groups**, 100.0% | $0.00 unclassified |
| the seal | **sealed by Tom Metzinger**, 12 Sep 22:50 | covers all 757, no drift |
| the rate | FRINGE **21.90%** · OVERHEAD 31.62% · G&A 12.37% · **INDIRECT_COMBINED 43.99%** | administrative labour on the **POOL** basis |
| the anchors | **4 of 4 tie** | every pool at `pool_variance` 0.00 |

**So Monday is a review, not a build.** The 757 judgments were recorded
through the API under Tom's name by `scripts/classification_log.py --apply`,
with `docs/CLASSIFICATION_LOG.md` as the written rationale beside each one.
What has *not* happened is a person reading them and affirming that they
stand. That is the substantive human step and it is step 2 below.

Three things are genuinely outstanding and none of them is classification:
the roster reply, the certifications, and the square footage. They are in
§P and they all belong to somebody other than the controller.

---

## 1 · Confirm the books still agree — Tom

**Gate: `POST /api/rates/compute` returns 409 while any of the eleven control
points is open.** All eleven tie today. This step is to confirm they still do.

`/reconcile` in the application, or:

```bash
python3 scripts/reconcile.py --base http://… # add --record only if it moves
```

**The one thing likely to have changed over the weekend** is the Bacon
$45,053.23 donor credit sitting in an intern wage account. When it is
reposted in QuickBooks the eleventh control moves — and the reconciling item
naming it has to come off with it, or the correction counts twice.

If a control has opened: close it by **naming** the difference, never by
netting it. `/api/reconcile/propose` finds the lines when exactly one
combination adds up, and proposes nothing at all when more than one would.
Then go to §C, because a reposting changes the ledger under a sealed set.

*Read `state`, never a variance of zero. Both sides of most controls are
`COALESCE(..., 0)`, so an empty period compares zero against zero and looks
green.*

## 2 · Review what stands — the controller team

**This is the work.** `/classify` is empty because the queue is finished; the
review happens against `docs/CLASSIFICATION_LOG.md`, which carries a reasoned
treatment for every one of the 757 groups with a citation and a rationale —
and now reads `already recorded · analysis of the lines` on each, so it says
both what was decided and why.

Start where the money is. Four judgments carry most of the weight:

| | | |
| --- | ---: | --- |
| `5227 Portfolio consulting` | $588,538.89 | in the base as **contractor** cost under 200.331, not a subrecipient. Reading it the other way takes the combined rate *up* to 50.23%. |
| `5010 Depreciation` | $850,382.89 | OVERHEAD, federal treatment **PENDING** — 200.436(b) cannot be answered until the asset register carries a funding source. |
| the wage accounts | $1,789,993.94 | **EXCLUDED**, deliberately: `compute` already feeds the payroll register into the base, so a DIRECT judgment here would count the labour twice. |
| `5108 Other Income` | $110,182.87 | EXCLUDED — $105,865.41 of it is a Q1 **2020** ERTC owed back under 200.406(b). |

If every judgment stands, nothing is required: the seal is current and so is
the rate. **Skip to §5.** If any judgment is wrong, go to §C.

## 3 · The seal — already held, and only Tom may move it

Sealed 12 September, covering all 757 live judgments, written 11 seconds
after the last one. `/rates` reads *Sealed by Tom Metzinger* from the record.

**Nothing to do unless something changes.** Sealing is the assertion that the
rate was not reverse-engineered; only `CONTROLLER` may seal or unseal and
nothing automated may do either.

## 4 · The rate — already computed, on the basis that was chosen

Four rates on file, all carrying the seal hash, all on the **POOL** basis.

**If you recompute for any reason, choose POOL again.** The screen defaults to
`OBJECTIVE`, which is what every rate before migration 068 used and gives
**34.82%** instead of 43.99% — nine points, on the same sealed judgments.
The basis is a choice on the screen under the seal, and it is recorded on the
rate so the workpaper says which was used.

## 5 · Check the stack — Tom

`/review/rate`. Every pool at `pool_variance` 0.00, all four `v_rate_anchor`
rows tying. **Nothing on that screen is computed** — every figure is read from
the row it was recorded in.

And read what it says above the figures: **no 200.465 facilities carve-out is
in this rate**, because no facility on the record carries measured space, so
every dollar of tenant and vacant occupancy cost sits in the federal pool.
43.99% reads high, which is the honest direction to err.

---

## C · If something has to change

The path the first version of this document did not have, and the one most
likely to be needed. Every step has a door in the application now.

1. **Unseal** — `/rates`, *Unseal…*, with a written reason. It supersedes
   every rate computed against that seal. The reason is required, because an
   unseal with no reason is a hole in the trail the seal exists to make.
2. **Correct the judgment** — `/classify`. Reclassifying supersedes rather
   than editing; the prior judgment is reversed and stays on the record.
3. **Re-seal** — the same act as before, over the corrected set.
4. **Recompute** — and choose **POOL** again (§4).
5. **Re-check** — §5. Then tell whoever has quoted the old figure, because
   43.99% is on every workpaper in `docs/`.

*Correct by superseding, never by editing. The record is append-only and a
position taken and then withdrawn is part of the trail.*

---

## P · Running in parallel, and none of it blocks the above

### The forty-three — their own timesheets

`/timesheet` offers each person the controller's reconstruction of their year,
pre-filled. **It is a convenience they may decline**, and the screen says so
before it says anything else. Three answers are all complete: type your own
days and ignore it; adopt it and correct any day that is wrong; or leave it.

**Adopting is not certifying.** Adopting puts hours on a sheet; signing says
the sheet is true, and that happens separately under `/certify`. Nobody signs
for anybody else — 200.430(i) wants the record of the person whose effort it
was, and a manager cannot sign on their behalf. `v_certification_chase` is a
list to go and ask, never an action.

**Blocked today: 0 of 43 certified, and no employment terms are on the record
for anyone**, so no draft can be built for anybody. That is the roster reply
coming back — the thing to go and get, not a fault in the system.

**Submitting does not move the rate.** Adopting the reconstruction faithfully
reproduces its shares, so the figures hold. If it did not, the rate would
depend on who had got round to signing.

### Kelly — the square footage

The single largest open item, and **it does not gate any classification**. In
the 2025 chart occupancy goes to OVERHEAD full stop; the tenant share comes
out at rate time as a 200.465 carve-out. `carved` reads 0.00 on a
$1,497,879.12 pool because no facility is measured.

At a realistic tenant share the combined rate is about **37.67%** rather than
43.99%. Nothing should go to NCDMM before this lands.

### Barb — the four decisions

`docs/BARB_ONE_PAGE_AM.pdf`. Whether YBI raises its own two credits first and
unprompted; who opens with NCDMM and when; pushing the 43 certifications; and
whether anybody looks at 2024.

---

## What must not be automated, and why

| | |
| --- | --- |
| **The seal** | It is the assertion that the rate was not reverse-engineered. A script that sealed would put the machine's name on it and the assertion would be worth nothing. |
| **A certification** | 200.430(i) wants the person whose effort it was. A signature nobody gave is the one lie that matters here. |
| **Adopting a draft** | Theirs to accept or decline. A pre-filled sheet that reads as an instruction produces forty-three signatures on somebody else's account of the year. |
| **A reconciling item** | A difference is closed by naming the lines behind it. A tolerance that quietly swallows a residual is how a system starts lying. |
| **Sending anything to NCDMM** | A position YBI takes with a sponsor, in writing. |

## If something goes wrong

- **Something was recorded by mistake.** `/api/undo` walks newest first. An
  undo that walked nothing back answers 409 with the reason. A sealed set
  refuses it — unseal first, per §C.
- **A screen reported success and nothing happened.** The failure panel in the
  shell now shows two records: what this browser saw fail, and what the
  *server* wrote down in `refusal`. They are not the same list — the second
  carries refusals from other sessions and other people.
- **A control cannot be evaluated.** `NO DATA` is not a pass. Say what it
  needs in order to mean anything.
