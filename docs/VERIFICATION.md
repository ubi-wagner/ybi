# Is it fit to present?

**13 September 2026.** Written because finding a significant defect while
building the Monday guidebook is evidence of a class, not an incident — and a
class that is not being checked has more instances in it.

**Short answer: yes for the Monday path, with two things named below that a
reader should hear from us rather than find.**

---

## What was run

| | |
| --- | ---: |
| unit, domain and structural tests | **1,194 pass** |
| `prove.sh` — eighteen steps, every drive, as all six people | **all pass** |
| `drive_ui.py` — 23 screens × 7 people in a real browser | **161 visits, 0 faults** |
| `test_every_capability_has_a_door.py` — every route against every call | **passes, 14 gaps recorded** |

Everything ran against sandboxes built from an empty database. The live
record was read and never written.

### The mechanical layer

```
drive_state_machine   7 turns, 78 checks — every turn moved what it should
drive_propagation     33 checks — and nothing it should not
drive_buildup         20 checks — the build-up ties at each step
drive_everyone        141 checks — every process, every change on the record
drive_access          73 checks — every boundary held
drive_actors          every boundary held, against real rows
drive_concurrency     16 checks, 0 findings
drive_requests        51 checks · drive_evidence 22 · drive_reverse 11
system review         0 faults, 1 gap, 33 notes
reconciliation        eleven cross-reference points tie
```

The single **gap** is the review correctly distinguishing *not working* from
*working over data nobody has supplied yet*: on a freshly seeded record
nothing downstream of the classification exists. That is the honest report,
not a failure.

### The browser layer — and why it was needed

`review_system.py` asks whether every route answers at the **API** level.
`walk_manuals.py` photographs screens. Neither watches what a screen *does*
when a person opens it, and that is where the defects have been living.

`drive_ui.py` opens every screen as every person and records every request the
page made and what came back, every console error, and whether anything was
drawn. Across 161 visits: **no 404, no 5xx, no unexpected console error**, and
**no screen offered in the nav that refuses the person it is offered to** —
which nothing had ever checked from a browser.

It has been watched failing. A deliberate typo in one route was caught for
all six signed-in actors, with the status and the path.

---

## What this pass found

### The class, not the instance

`POST /api/rates/compute` had no door — complete on the server, named in a
comment on the screen that should have called it, reachable only by running a
script. It was the **fourth** instance of that shape in this system's history:
the restatement's five routes with no page, the timesheet draft's two with no
card, the lane comparison that could only answer zeroes, then the rate.

Every one was found by somebody reading one area closely. So the answer was
not to look harder for the fifth:
`tests/test_every_capability_has_a_door.py` derives the routes from the
running application and the calls from the SPA and keeps no list of either.

**It found fourteen more.** Two were on the Monday path and now have doors:

| | |
| --- | --- |
| `POST /api/rates/unseal` | **the runbook's own recovery step.** "A judgment was wrong after sealing: unseal with a written reason, which supersedes the rate." Nothing in the application could. |
| `GET /api/dashboard/refusals` | the refusal register. The failure panel has always claimed *"every one of these is also on the record server-side"* and had no way to show it. |

The other twelve are real and **none is on the Monday path**. They are
recorded in `NO_DOOR_YET` with the screen each belongs on, kept separate from
the routes that will never have one — because *"this will never have a
screen"* and *"nobody has built the screen yet"* lead to different work.

### Other defects fixed this pass

- **`prove.sh` ran the manual tests before the step that produces what they
  assert on**, so an interrupted walk made the next run fail on an artefact
  the same script was about to regenerate. In the one place a reviewer looks
  to decide whether the system holds.
- **A test asserting a literal line rather than the rule it describes.** The
  failure panel's guard was pinned to exact source, so growing a second
  source broke it while the rule — absent when there is nothing to say — was
  obeyed perfectly. It holds the rule now, and additionally fails if the
  panel renders a list the guard does not cover.
- **The rate screen said "Before sealing" over a sealed set** carrying four
  rates, and had no way to know it was sealed — the endpoint did not say.
- **The compute button applied a policy nobody chose.** Sending an empty body
  computed 34.82% on the OBJECTIVE basis — the default, correctly, and not
  the basis this engagement settled on. The choice is on the screen now.

### Four defects in the instruments themselves

Worth stating plainly, because an instrument that cries wolf is worse than no
instrument: it teaches the reader the list is wrong, and the next real finding
they dismiss.

The route matcher substituted `{...}` before `${...}` and reported sixty live
routes as unreachable; it was not brace-aware and read the Library as
unreachable; it scanned only `api.js` and read every CSV export as unreachable
when a download link is a door too. And the browser sweep counted every
signed-out 401 and every correct 403 as a fault, which made twenty-three
working refusals look like defects. All four were found and fixed before any
finding was reported.

---

## What a reader should hear from us

**Two things, and neither is a defect.**

1. **The rate is a working figure.** No 2 CFR 200.465 facilities carve-out has
   ever been evaluated, because no facility on the record carries measured
   space. Every dollar of tenant and vacant occupancy cost sits in the federal
   pool, so 43.99% reads high — which is the honest direction to err, and it
   falls to about 37.67% when Kelly's measurement lands.
2. **Nothing has been done on anybody's behalf.** 0 of 43 effort
   certifications are signed and no employment terms are on the record, so no
   pre-filled timesheet can be built for anyone yet. That is the roster reply
   coming back, not a fault — and the certifications are a signature nothing
   but a person may produce.

## What I would not claim

- That the twelve remaining doorless routes do not matter to somebody
  eventually. They are a backlog, written down, and the list can only shrink
  by somebody doing the work.
- That a sweep proves correctness. It proves the screens reach the server and
  the server answers. The *figures* are held by the eleven reconciliation
  controls, the four rate anchors and `pool_variance`, all of which tie.
- That Monday will go as the guidebook shows. The guidebook shows a sandbox
  built from empty. If QuickBooks reposts the Bacon credit over the weekend,
  control eleven opens and step 1 is real work rather than a formality.

---

*Regenerate any of this:* `./scripts/prove.sh`, `scripts/drive_ui.py`,
`pytest tests/test_every_capability_has_a_door.py`.
