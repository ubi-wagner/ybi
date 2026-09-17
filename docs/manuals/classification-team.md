# Working the classification, and the timesheets under it

*For the people helping Tom close 2025 — anybody holding `CONTROLLER`, and
everybody on the payroll for the timesheet half.*

The 2025 ledger is **already classified**. All 757 cost groups carry a
position, 100% of the dollars, and a rate has been computed from them. What
they are *not* is anybody's judgment yet.

That distinction is the whole of your job.

---

## 1. Why there are 757 positions nobody has judged

`scripts/classification_log.py --apply` walked the whole year a month at a
time and recorded a reasoned treatment for every group — the pool, the 990
function, the federal treatment, the objective, and a citation and rationale
on each. It wrote them through the real API, signed in as Tom, so every one
carries his name and an audit row.

That is the right way for a script to write and it is also the problem: **all
757 read `decided_by = 'Tom Metzinger'` and were recorded across six
seconds.** An auditor reading the timestamps finds seven hundred judgments a
minute and stops trusting the file.

So each carries `origin = MACHINE_PROPOSAL` — a *working position*, not a
judgment — and `/classify/review` is where they become judgments.

**Adopting moves no figure.** Confirming a position writes a row in a
different table and does not touch the decision, the seal or the rate. The
rate is the same before and after, which is the property that makes it safe
to do 757 of them: it can never depend on who got round to reviewing.

## 2. Reviewing them

**`/classify/review`.** Twenty-five at a time, with *Adopt the 25 shown*,
because adopting 756 one at a time is not a job anybody does and a screen
that only offered that is one people work around by sealing without reviewing
— which is the thing the whole exercise is against.

For each position you see the account, the payee, the amount, the four
dimensions the log chose and **the rationale it chose them for**. Three
outcomes:

| what you think | what you do |
| --- | --- |
| that is right | Adopt |
| that is wrong | **Recommend** the change, with a note. It goes on Tom's list; he disposes of it |
| I want to say something without changing it | **Note** it — see below |

### The eighty-six the log would not judge

The log blocked $3.9m of the $10.2m and **every block names the thing to go
and get**. "Cannot be classified" on its own is a dead end, so a test fails a
block whose reason is too short to act on. The big ones:

| | |
| --- | --- |
| **$2,475,106** | `5227 Portfolio consulting` — whether supporting portfolio companies is programme delivery or YBI's own business development |
| **$850,383** | depreciation — 200.436(b) needs the funding source, which is Heidi's screen |
| **$283,761** | intern wages, carrying the $45,053.23 donor credit not yet reposted in QuickBooks |
| **$110,183** | Other Income, of which $105,865.41 is a Q1 **2020** Employee Retention Tax Credit from Staffmark — due back to the 2020 awards under 200.406(b) |
| **$88,870** | splits that genuinely cross pools |
| **$71,797** | cost objectives that do not exist — ARC Arise and SBA Growth Accelerator have no `cost_objective` row |
| **$57,596** | the insurance policy schedule. Both halves are indirect, so this moves the OVERHEAD/G&A split and not the combined rate |

### Two kinds of note, and the choice is made once

* a **RECORD** note is part of the cost record, read by everybody entitled to
  read it, and it travels in the audit package;
* a **WORKING** note is deliberative and does not.

**There is no show/hide switch, on purpose.** A switch is something somebody
can flip the day after an auditor asks for the file, and the flip — not the
note — is the finding. The kind is decided when the note is written.

A working note is **undisclosed and never concealed**: the auditor is not
shown the text and *is* shown that it exists. Dropping the row would make
three notes look like one.

## 3. The four things a classification says

| | |
| --- | --- |
| **Pool** | DIRECT, FRINGE, OVERHEAD, G&A, FUNDRAISING, UNALLOWABLE, EXCLUDED, RENTAL_DIRECT |
| **990 function** | PROGRAM, MANAGEMENT_AND_GENERAL, FUNDRAISING, NOT_APPLICABLE |
| **Federal treatment** | ALLOWABLE, UNALLOWABLE, PENDING |
| **Objective** | required where the pool is DIRECT, refused where it is not |

Four traps worth knowing before you change one:

* **`EXCLUDED` is not "this is not cost".** It is the enum's word for cost
  the pools must not carry. The wage accounts are EXCLUDED because
  `compute` already puts the labour distribution into MTDC through
  `add_labor()`; a DIRECT judgment on `5140 Employee Wages` would count the
  whole payroll twice and every indirect rate would read low by its width.
* **`EXCLUDED` says nothing about the 990.** Which pool carries a salary and
  which column of the return it goes in are two questions. The return's
  compensation split comes from the effort distribution, not from the pool.
* **`PENDING` is a real answer.** Depreciation belongs in OVERHEAD and its
  allowability is genuinely open until the funding source lands. PENDING puts
  the cost where it belongs and leaves the claim open, which is what is true.
* **DIRECT names an objective and nothing else may.** It is an equivalence,
  so a change of pool away from DIRECT takes the objective with it.

## 4. Citing the document

This is the one step of the walk still open on the 2025 record: **0 of 363
federally chargeable judgments cite a document.**

**Attaching is not citing, and the difference decides a grade.** Attaching
says *this paper is about that money*. Citing says *this paper is why I
judged it the way I did*. `VERIFIED` counts citations, so bulk attachment
raises nobody's grade — it makes the document findable, and the citation is
carried on the judgment.

`/evidence` proposes matches. **Amount is necessary and nothing else is
sufficient**: a document proposes only where its amount equals a candidate's
to the cent, and date proximity and vendor similarity break ties. **More than
one candidate means no candidate** — and the screen tells you how many tied
rather than saying nothing was found.

---

## 5. The timesheets

Every one of the 43 people in the 2025 labour distribution carries
`NEEDS_CERTIFICATION` at BLOCKING, and the whole $1,835,047.17 is
`MANAGEMENT_RECONSTRUCTION`. That does not change a figure in the rate. It
changes whether the rate is **usable**, because 2 CFR 200.430(i) goes to the
allowability of the entire direct labour charge.

### The goal is not to invent 2025 timesheets

200.430(i) does not require a contemporaneous record. It requires one that
reflects the work actually performed, is supported, and is reviewed after the
fact. **A reconstruction the person reads, corrects and signs meets that. A
reconstruction nobody ever saw does not**, which is where 2025 has been.

### The path, per person

1. **Get an account.** Thirty-seven of the forty-three have none. The sign-in
   card's second tab opens one against an `@ybi.org` address and the
   organisation's password — the account is opened on YBI's own payroll key
   where the `surname@ybi.org` convention matches, and says so in the audit
   row where it does not.
2. **Choose your own password.** Nothing can be written on a password
   somebody else chose — not a classification, not a timesheet, not a
   certification. The one exception is changing it.
3. **Open `/timesheet`.** The draft card shows the controller's
   reconstruction of your year: which projects, how many hours, spread across
   the working days of each month at 8.00 hours a day. Where the hours log
   has your months it uses them; where it does not it shows the year and says
   so.
4. **Read it and correct it.** YBI's calendar counts every weekday as
   available and takes no holiday out, so nothing in the draft separates a
   day you were off from a day you worked. **Move any holiday, vacation or
   sick day to Paid leave before you submit.** You do not lose those wages:
   `LEAVE` is not a final objective, so the distribution spreads them back
   across the work you did.
5. **Adopt, then submit, then certify.**

### What adopting does and does not do

* It writes the entries **under your own name**. There is no parameter naming
  anybody else and the route does not take one.
* It records `basis = ADOPTED`, which grades `MANAGEMENT_RECONSTRUCTION` —
  the grade the reconstruction already held, **carried across, not raised**.
  Signing adds no document, so it cannot add documentary support. What it
  strengthens is the certification status, which is a different column.
* `RECALL` is what a day typed from memory carries and it stays
  `UNSUPPORTED`. Nobody can choose `ADOPTED` by hand; only the adopt route
  writes it.
* **The rate does not move.** Adopting reproduces the reconstruction's shares
  faithfully, so it must not — otherwise the rate would depend on who had got
  round to signing.

### A manager cannot sign for somebody — and can file a page they signed

200.430(i) wants the person whose effort it was, so nobody signs on anybody's
behalf. `v_certification_chase` is a project manager's list of **who to go and
ask**, never an action. "Their projects" is read from the assignments they
made.

What you *can* do is file the page they signed. Thirty-seven of the
forty-three have no account, and waiting for each of them to sign on a screen
is waiting on an account somebody has to open first — while the signed sheet
sits in a folder. **Time · a row · File signed**, on the roster, takes the
scan and the date the page carries, and records:

| | |
| --- | --- |
| `signed_by` | **them** — read off the record, never typed |
| the account and session | **you**, because you filed it |
| the page | mandatory; the row cannot exist without it |
| the date on the page | kept apart from the date you filed it |

Three things to know before you use it.

**It is not a supervisor certification.** That is *you* asserting firsthand
knowledge of their work, in your own words, and it says so on the record. This
is you relaying what they asserted. The route refuses a request that claims
both.

**The page is not optional and not a formality.** A row saying somebody signed
with nothing to check it against reads as a certification on every screen and
in the audit package. The schema refuses it — `paper_names_its_page` — and so
does the screen, before you get that far.

**Do not put today's date in.** Put the date on the sheet. The gap between the
two is the filing lag, and a reviewer is entitled to see it; collapsing them
into one column throws away the only fact that says how long the page sat
before it reached the record.

A person who later signs on screen themselves does not cancel this — both
stand, and the roster says which kind it counted.

### Uncertified is not blocked, and every paper says so

You can produce a workbook, regenerate an invoice, run the return and compute
a rate with none of this done. That is the design rather than a shortcut:
testing against real figures is ordinary work and a machine that refused it
is one people route around. What changes is **what the paper says** — every
document carries a band reading `NOT CERTIFIED` and the reason, or naming who
signed and when, and repeats the walk's unfinished steps above its figures.

This run was produced that way, and the band is worth reading rather than
trusting. It has three states, not two: **certified** names who signed and
when; **NOT CERTIFIED** gives the reason, which is usually that the rate has
been recomputed since somebody signed and the signature is on a build-up that
no longer stands; and **REHEARSAL** means a drive produced that signature to
prove the mechanism and no person gave it. The third exists because one did,
and 53 published documents said *CERTIFIED — Tom Metzinger* over a rate
nobody had put their name to.

Whatever it says, the citations are a separate fact and it prints that too.
