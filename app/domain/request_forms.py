"""What we are still asking YBI for, defined once.

Three things are missing from the record and none of them can be inferred:
which assets the government already paid for, who uses which square foot, and
the email address of thirty-seven people who have to sign their own effort.
Each has a lead time measured in weeks and each is somebody else's filing
cabinet, so the ask has to be *easy to answer* — a workbook with the answer
half written already, not a list of questions.

**The form is defined once and both directions read it.** The writer builds
the workbook from these columns and the parser reads a filled one back through
the same definition, so a workbook cannot ask for a column the parser does not
accept. That failure mode is not hypothetical here: the same shape produced
two coverage figures six-fold apart, and a nav stricter than the API.

Three rules run through every form:

**A blank is a blank.** Never zero, never false, never "not federal". The
parser reports "not answered" as its own state, because the intake version of
*unclassified cost is never defaulted into a pool* is that an unanswered
question is never defaulted into an answer. Somebody who left the funding
column empty on forty assets has told us nothing forty times, and the record
should say exactly that.

**Ask only for what only they know.** Everything already on the balance sheet
or in the payroll register is filled in before the workbook is sent. The
person is confirming and completing, not transcribing — and a form that makes
somebody retype what we already hold is a form that comes back late and wrong.

**Every column says what turns on it.** Not "Funding source" but "Funding
source — 2 CFR 200.436(b) makes depreciation on the federal share
unallowable; this column decides roughly $327,000." People answer a question
they understand the consequence of.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class Kind(StrEnum):
    """How a cell is read. The heading says which, so there is nothing to
    infer at the point of reading it."""
    TEXT = "TEXT"
    NUMBER = "NUMBER"
    MONEY = "MONEY"
    PERCENT = "PERCENT"      # 0 to 100, stated on the sheet, never a fraction
    DATE = "DATE"
    CHOICE = "CHOICE"
    YES_NO = "YES_NO"


@dataclass(frozen=True)
class Column:
    key: str
    heading: str
    kind: Kind
    #: Required means the row is not usable without it, and the preview will
    #: say so. It does not mean the workbook refuses to save — a half-filled
    #: workbook coming back is information, and refusing it at the door would
    #: mean waiting another week for the whole thing.
    required: bool = False
    why: str = ""
    citation: str = ""
    choices: tuple[str, ...] = ()
    width: int = 18
    #: Filled in before the workbook is sent. The person confirms or corrects
    #: it; they do not type it.
    known: bool = False


@dataclass(frozen=True)
class Control:
    """Something the answers have to tie to, printed on the first sheet.

    A control here is the same idea as one on the reconciliation register: a
    figure we already hold that the answer must agree with. It is checked at
    preview and reported, never enforced at the door — a register that arrives
    $400 out is a conversation, not a rejection.
    """
    label: str
    column: str
    expect: Decimal | None = None
    note: str = ""


@dataclass(frozen=True)
class Form:
    name: str
    version: int
    title: str
    for_whom: str
    #: Why this is being asked, in the words of somebody who will have to
    #: spend an afternoon on it.
    purpose: str
    #: What it changes if it arrives, and what happens if it does not.
    consequence: str
    sheet: str
    columns: tuple[Column, ...]
    controls: tuple[Control, ...] = ()
    #: Printed above the grid. Short: anything long goes on the first sheet.
    instructions: tuple[str, ...] = ()
    #: The columns we fill in before sending. A row where *only* these are
    #: answered came back exactly as it went out, which is a queue rather
    #: than a half-finished row — and the two want different chasing. Without
    #: this the two hundred and sixty-three assets we send out pre-filled all
    #: read as "somebody started this and gave up".
    prefilled: tuple[str, ...] = ()

    def column(self, key: str) -> Column | None:
        return next((c for c in self.columns if c.key == key), None)

    @property
    def required(self) -> tuple[Column, ...]:
        return tuple(c for c in self.columns if c.required)


# ── The funding kinds and space uses, lifted from the schema ──────────
#
# Typed against the same vocabulary the database enforces, so the dropdown a
# person is offered and the value the column accepts cannot drift apart. A
# free-text funding source is how you end up with "EDA grant (I think)" in a
# column the allowability test reads.

FUNDING_KINDS = ("FEDERAL", "STATE", "LOCAL", "PRIVATE", "DEBT", "UNRESTRICTED")
SPACE_USES = ("TENANT", "PROGRAM", "ADMINISTRATIVE", "SHARED_LAB",
              "COMMON", "VACANT", "COMMITTED")
OCCUPANCY = ("OCCUPIED", "VACANT", "INTERNAL", "COMMITTED", "COMMON")


# ── 1. The asset register ─────────────────────────────────────────────

ASSET_REGISTER = Form(
    name="ASSET_REGISTER",
    version=1,
    title="Fixed asset register, with funding source",
    for_whom="whoever holds YBI's fixed asset records",
    purpose=(
        "YBI carries $23,189,122.50 of gross depreciable basis against $6.74M "
        "of annual expense, and $850,382.89 of that basis ran through 2025 as "
        "depreciation. Whether a given dollar of that depreciation may be "
        "recovered from a federal award depends on one thing: whether federal "
        "money paid for the asset in the first place. Nothing else in the "
        "file answers it."),
    consequence=(
        "Tech Block Building 5 alone is 38.5% of the depreciable basis. If it "
        "was publicly funded, roughly $327,000 of 2025 depreciation is "
        "unallowable and the indirect rate falls about 2.9 points. Until this "
        "register arrives the rate is computed as though none of it was "
        "funded, which overstates it — the honest direction to be wrong, and "
        "not a direction anyone wants to defend in an audit."),
    sheet="Assets",
    prefilled=("asset_id", "description", "gl_account", "in_service_on",
               "gross_cost", "book_cost", "useful_life_years",
               "accum_depr_close", "depreciation", "note"),
    instructions=(
        "One row per asset. The six grey rows are the balance sheet totals we "
        "already hold — please replace each with the individual assets that "
        "make it up, or tell us the register is kept somewhere else.",
        "Leave a cell blank if you do not know. A blank is recorded as "
        "unanswered; a zero is recorded as an answer.",
        "Original cost means before any grant reimbursement was netted "
        "against it. See the note on the first sheet — this is the one that "
        "matters most.",
    ),
    columns=(
        Column("asset_id", "Asset ID or tag", Kind.TEXT, required=True,
               why="Anything stable and unique. Your own tag number is ideal.",
               citation="2 CFR 200.313(d)(1)", width=20),
        Column("description", "Description", Kind.TEXT, required=True,
               why="What it is, in the words you would use to find it.",
               citation="2 CFR 200.313(d)(1)", width=42),
        Column("serial_number", "Serial or VIN", Kind.TEXT,
               why="Where one exists. Buildings will not have one.",
               citation="2 CFR 200.313(d)(1)"),
        Column("gl_account", "GL account", Kind.TEXT, known=True,
               why="Which balance sheet account it sits in.", width=34),
        Column("title_holder", "Who holds title", Kind.TEXT,
               why="Federally titled property carries disposition conditions "
                   "that outlive the award.",
               citation="2 CFR 200.313(d)(1)", width=24),
        Column("acquired_on", "Acquired", Kind.DATE,
               why="Date of purchase or completion."),
        Column("in_service_on", "Placed in service", Kind.DATE,
               why="Depreciation runs from here, and an asset not in use is "
                   "not depreciable at all.",
               citation="2 CFR 200.436"),
        Column("gross_cost", "Original cost, before any reimbursement",
               Kind.MONEY, required=True,
               why="Finding 2024-001 says capital reimbursements were netted "
                   "against asset cost, so book value understates the basis. "
                   "We need the figure before the netting.",
               citation="2 CFR 200.313(d)(1)", width=22),
        Column("book_cost", "Cost as currently on the books", Kind.MONEY,
               why="So the two can be bridged rather than one replacing the "
                   "other silently.", width=22),
        Column("federal_amount", "Federal money in it", Kind.MONEY,
               why="How many dollars of the original cost came from a federal "
                   "award. Blank means unknown; 0 means you have checked and "
                   "there is none.",
               citation="2 CFR 200.436(b)", width=20),
        Column("federal_award_reference", "Federal award number / FAIN",
               Kind.TEXT,
               why="EDA, ARC, or whichever. The number on the award document.",
               citation="2 CFR 200.313(d)(1)", width=26),
        Column("state_amount", "State or local money in it", Kind.MONEY,
               why="The Ohio Board of Regents and Vindicator money both carry "
                   "use conditions of their own.", width=20),
        Column("state_award_reference", "State award number", Kind.TEXT,
               width=24),
        Column("counted_as_cost_share", "Was this counted as cost share?",
               Kind.YES_NO,
               why="If non-federal money in this asset was already pledged as "
                   "cost share on a federal award, depreciating it into a "
                   "federal pool may recover the same dollars twice.",
               width=26),
        Column("useful_life_years", "Useful life (years)", Kind.NUMBER),
        Column("accum_depr_close", "Accumulated depreciation at 31 Dec 2025",
               Kind.MONEY, width=24),
        Column("depreciation", "2025 depreciation", Kind.MONEY, width=20),
        Column("facility_name", "Which building", Kind.TEXT,
               why="Drives the occupancy carve-out.", width=26),
        Column("disposed_on", "Disposed", Kind.DATE,
               why="Leave blank unless it went.",
               citation="2 CFR 200.313(e)"),
        Column("last_inventory_on", "Last physical inventory", Kind.DATE,
               why="Required at least every two years, independently of any "
                   "of this.",
               citation="2 CFR 200.313(d)(2)"),
        Column("note", "Anything we should know", Kind.TEXT, width=46),
    ),
    controls=(
        Control("Original cost of every asset listed", "gross_cost",
                Decimal("23189122.50"),
                "The gross depreciable basis on the 31 December 2025 balance "
                "sheet. Land (107,530.00) and construction in progress "
                "(438,355.19) are excluded — do list them, we will exclude "
                "them again."),
        Control("2025 depreciation", "depreciation", Decimal("850382.89"),
                "Account 5010 on the profit and loss."),
    ),
)


# ── 2. Space, and who uses it ─────────────────────────────────────────

SPACE_INVENTORY = Form(
    name="SPACE_INVENTORY",
    version=1,
    title="Floor space, and who uses it",
    for_whom="whoever holds the floor plans and the rent roll",
    purpose=(
        "Occupancy is the second largest item in the indirect cost pool. "
        "Space rented to a tenant, space standing empty, and space promised "
        "to somebody else are all costs of the rental operation and never "
        "reach a federal award — but only a floor plan can say which square "
        "feet those are."),
    consequence=(
        "With no space on file the carve-out under 2 CFR 200.465 cannot be "
        "computed at all, so overhead currently carries the tenant and vacant "
        "space along with everything else. The rate reads high. Between this "
        "and the asset register the modelled range is 36% to 46%, and the "
        "spread is almost entirely these two."),
    sheet="Space",
    prefilled=("facility_name", "label", "occupant", "use", "status",
               "actual_annual_charge", "note"),
    instructions=(
        "One row per suite, lab, or identifiable area. Corridors, restrooms "
        "and mechanical space go in as COMMON — they are real square feet and "
        "leaving them out makes everything else look larger than it is.",
        "The square feet in each building have to add up to the building's "
        "usable area. The first sheet lists what we have for each building; "
        "if that figure is wrong, correct it there.",
        "Months occupied matters: a suite empty for half the year is half a "
        "suite of cost, and that is how it will be counted.",
    ),
    columns=(
        Column("facility_name", "Building", Kind.TEXT, required=True,
               why="Use the same name for every row in the same building.",
               width=28),
        Column("label", "Suite or area", Kind.TEXT, required=True,
               why='Whatever it is called on the plan — "Suite 210", "Lab 1".',
               width=24),
        Column("floor", "Floor", Kind.TEXT, width=10),
        Column("usable_sqft", "Usable square feet", Kind.NUMBER, required=True,
               why="From the plan, not from the lease — a lease often states "
                   "rentable feet, which include a share of the common area "
                   "and would double-count it here.",
               width=18),
        Column("use", "What it is used for", Kind.CHOICE, required=True,
               choices=SPACE_USES,
               why="TENANT is leased to a third party. PROGRAM is delivering "
                   "one named programme. COMMITTED is promised to somebody "
                   "under an agreement, like the YSU joint use space.",
               citation="2 CFR 200.465", width=20),
        Column("status", "Occupied or empty", Kind.CHOICE, required=True,
               choices=OCCUPANCY, width=18),
        Column("occupant", "Who is in it", Kind.TEXT,
               why="The tenant's name, or the team. Required where the status "
                   "is OCCUPIED.", width=28),
        Column("objective_id", "Which programme", Kind.TEXT,
               why="Only where the use is PROGRAM. The programme name as you "
                   "use it — we will match it.", width=24),
        Column("months_occupied", "Months occupied in 2025", Kind.NUMBER,
               why="12 unless it changed hands or stood empty part of the "
                   "year.", width=20),
        Column("actual_annual_charge", "Charged for it in 2025", Kind.MONEY,
               why="What was actually billed. Blank if nothing was.",
               width=20),
        Column("market_rate_psf", "Market rate per square foot", Kind.MONEY,
               why="What comparable space in Youngstown lets for. Only if you "
                   "have a basis for it — the next column.", width=22),
        Column("market_basis", "Basis for that rate", Kind.TEXT,
               why="A broker's opinion, a comparable lease, an appraisal. A "
                   "rate with no basis behind it is a number somebody made "
                   "up, and the system will not accept one.", width=44),
        Column("note", "Anything we should know", Kind.TEXT, width=40),
    ),
)


# ── 3. The people who have to sign ────────────────────────────────────

PEOPLE_ROSTER = Form(
    name="PEOPLE_ROSTER",
    version=1,
    title="Employee roster — working email addresses",
    for_whom="whoever administers payroll or IT accounts",
    purpose=(
        "2 CFR 200.430(i) wants a statement from the person whose effort it "
        "was. Nobody may sign on their behalf — not a manager, not the "
        "controller. So every person who worked on a federal award in 2025 "
        "needs an account, and an account needs an address somebody has "
        "confirmed."),
    consequence=(
        "Thirty-seven of forty-three people on the payroll register have no "
        "confirmed address, so they cannot certify. Until they can, the "
        "labour evidence behind the fringe base is a reconstruction that "
        "names its sources — defensible, but not a certification. This is the "
        "longest lead time of anything outstanding: it is the item to start "
        "today."),
    sheet="People",
    prefilled=("employee_key", "surname", "note"),
    instructions=(
        "The names come from the 2025 payroll register, which carries "
        "surnames only. Please complete the first name and a working email "
        "address for each.",
        "Where somebody has left, say so in the last column rather than "
        "deleting the row — they still worked the hours, and their "
        "certification is still wanted if they can be reached.",
        "An address that was guessed from a naming convention is worse than "
        "a blank one: it will bounce, or worse, it will not.",
    ),
    columns=(
        Column("employee_key", "Payroll ID", Kind.TEXT, required=True,
               known=True, why="As it appears on the register. Please do not "
                               "change it — it is how the hours join up.",
               width=18),
        Column("surname", "Surname", Kind.TEXT, known=True, width=22),
        Column("first_name", "First name", Kind.TEXT, required=True, width=20),
        Column("email", "Working email address", Kind.TEXT, required=True,
               why="The one they actually read.", width=34),
        Column("job_title", "Job title", Kind.TEXT, width=30),
        Column("still_employed", "Still employed?", Kind.YES_NO, width=16),
        Column("note", "Anything we should know", Kind.TEXT, width=40),
    ),
)


#: Appended to every form by the writer and read back by the parser.
#:
#: Whether a row came back untouched cannot be told from its contents: we
#: send two hundred and sixty-three assets out with the description and cost
#: already in them, and a person adding a two hundred and sixty-fourth types
#: into exactly those columns. So the workbook says which rows it issued,
#: rather than the parser guessing — and the column is locked and grey, which
#: is also what explains the grey to the person filling it in.
ISSUED_MARKER = Column(
    "issued_row", "Sent pre-filled", Kind.TEXT, known=True, width=14,
    why="Ours. It marks the rows that went out with figures already in them, "
        "so we can tell what you changed from what you added. Leave it blank "
        "on any row you add.")

ISSUED = "YBI"


FORMS: dict[str, Form] = {f.name: f for f in
                          (ASSET_REGISTER, SPACE_INVENTORY, PEOPLE_ROSTER)}
