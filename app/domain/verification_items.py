"""The nineteen things the record cannot settle on its own.

Moved here out of `scripts/verification_sheet.py` when the request forms
needed the same list. **Two copies of one list is the shape that produced
13.0% and 2.2% at the same moment**, and a third — a workbook, a printable
worksheet, and now a form that takes the answers back — would have been the
worst of them, because the third would silently stop matching the first two
the day somebody added an item.

So there is one list and everything reads it:

    scripts/verification_sheet.py   the workbook and the printed worksheet
    app/domain/request_forms.py     the VERIFICATION form that takes it back
    docs/FOR_TOM_TO_VERIFY.md       the narrative, checked against it by
                                    tests/test_verification_sheet.py

The narrative has to be prose and the form has to be structured, so neither
can be derived from the other — which is exactly why the references are
tested rather than trusted.

Pure data. No database, no imports from `app.db`, like everything else in
`domain/`.
"""

from __future__ import annotations

from dataclasses import dataclass


#: What a person may say about an item. Deliberately short, and deliberately
#: not just yes/no: "I have checked and the record is right" and "I have
#: corrected it" lead to different work at our end, and "somebody else has to
#: answer this" is a real outcome that otherwise looks like silence.
STATUS = (
    "CONFIRMED — the record is right",
    "CORRECTED — I have changed something",
    "STILL CHECKING",
    "SOMEBODY ELSE HAS TO ANSWER",
    "NOT APPLICABLE",
)


@dataclass(frozen=True)
class Item:
    ref: str
    area: str
    title: str
    figure: str
    #: What the record shows, in one or two sentences.
    found: str
    #: The question, in Tom's words.
    asks: str
    #: What turns on it.
    moves: str
    answered: tuple[str, str, str] = ()      # status, answer, by — worked example


ITEMS: tuple[Item, ...] = (
    Item("0", "Example", "The Bacon $45,000 — confirmed", "45,000.00",
         "A pledge from Vince and Phyllis Bacon to fund interns was booked as "
         "a credit against 5142 Intern Wages rather than as contributions "
         "income. Ten of the eleven cross-reference controls were blind to it; "
         "only the payroll register could see it.",
         "Confirmed on 11 September 2026. Still open: the entry has not been "
         "reposted in QuickBooks. When it is, tell us — the reconciling item "
         "has to come off with it, and the two must not both be there.",
         "Fringe rate: 22.45% against the defensible 21.90%.",
         ("CONFIRMED — the record is right",
          "Confirmed 11 Sep 2026. QuickBooks entry still to be reposted.",
          "Tom Metzinger")),

    Item("1.1", "Depreciation",
         "Three reimbursements netted against Tech Block Building 5",
         "157,739.00",
         "The 2026 asset schedule carries Fitz Reimbursement −117,739.00 "
         "(30 Jun 2019), NCDMM Reimbursement −25,000.00 (26 Sep 2019) and YSU "
         "Reimbursement −15,000.00 (31 Dec 2019) against Building 5. This is "
         "Finding 2024-001 in the flesh.",
         "Is the recorded cost of Building 5 gross or net of these three? And "
         "is NCDMM's $25,000 federal money?",
         "If the cost is net, the gross basis is understated and the federal "
         "share cannot be derived from the books at all."),

    Item("1.2", "Depreciation",
         "Two aggregates the register's own totals exclude", "1,516,695.00",
         "BUILDINGS at 180,000.00 and CAPITAL IMPROVEMENTS at 1,336,695.00 are "
         "printed on their sheets and left out of the Total Cost/Basis those "
         "sheets carry. They look like opening aggregates the itemised rows "
         "below them replaced.",
         "Confirm these were superseded by the detail rather than dropped by "
         "accident.",
         "Reading them as assets overstates the basis by $1.5m; dropping them "
         "silently is a $1.5m hole nobody could see."),

    Item("1.3", "Depreciation",
         "The register is above the balance sheet", "122,921.14",
         "Register 23,419,573.64 plus construction in progress 438,355.19 = "
         "23,857,928.83, against gross fixed assets of 23,735,007.69 on the "
         "31 December 2025 balance sheet.",
         "Can we have the register as at 31 December 2025? Failing that, "
         "confirm the 122,921.14 is 2026 additions.",
         "The register is a 2026 export, so this is probably timing — and the "
         "rate should not rest on 'probably'."),

    Item("1.4", "Depreciation", "Depreciation differs", "22,429.02",
         "2025 P&L account 5010 reads 850,382.89. The register's Current "
         "Depreciation totals 872,811.91.",
         "Same likely cause as 1.3 — a 2026 export — and the same answer "
         "settles both.",
         "The depreciation figure feeds the facilities pool directly."),

    Item("1.5", "Depreciation", "Xjet Ceramic Printer carried at zero", "0.00",
         "System no. 174, in service 25 January 2018, seven-year life, cost "
         "0.00, no accumulated and no current depreciation. A real number and "
         "a real date with no money against them. There is also an XJET cost "
         "objective on the record.",
         "Donated? Fully reimbursed and netted, like 1.1? Or written off?",
         "An asset at zero that should carry cost is missing basis."),

    Item("1.6", "Depreciation", "Two True Up Entry rows", "16,931.13",
         "On the Building 5 sheet, dated 30 and 31 December 2019, carrying "
         "accumulated depreciation of 7,173.29 and 9,757.84 and no cost at all.",
         "What were these correcting?",
         "Accumulated depreciation with no asset behind it distorts net book "
         "value by class."),

    Item("2.1", "The books",
         "Every ledger-to-P&L difference is Rising Tides", "7,469.87",
         "Five accounts differ and all five are one account bleeding into four "
         "others: Rising Tides +7,469.87 against ESP −6,300.00, Travel "
         "−622.26, Advertising −280.40 and Staff Training −267.21. Ten "
         "specific lines, all named on the record.",
         "Were these reclassified out of Rising Tides after the general ledger "
         "was exported and before the P&L was?",
         "If yes the record is right as it stands. If not, one of the two "
         "exports is wrong."),

    Item("2.2", "The books", "Is Rising Tides federally funded?",
         "1,386,355.56",
         "The objective master says not federal. The controller's workbook "
         "says it is. 137 ledger lines.",
         "Which is right, and what is the award?",
         "Changes the SEFA and the scope of the Single Audit — not just a "
         "rate. The biggest open question outside depreciation."),

    Item("2.3", "The books", "4801 IH Grant Income", "451,170.39",
         "The P&L reports it under Innovation Hub. The revenue ledger "
         "attributes it to NCDMM.",
         "Which? ",
         "If it is not America Makes money, the America Makes reconciliation "
         "changes by nearly half a million dollars."),

    Item("2.4", "The books", "Hybrid is out by a hundred dollars", "100.02",
         "P&L revenue 3900 Grant Income:Hybrid Energy reads 191,638.05. The "
         "grant tabs read 191,738.17.",
         "Which is right?",
         "Small, and Hybrid's over-billing conclusion stands either way — but "
         "worth closing rather than leaving in a workpaper."),

    Item("3.1", "Space", "Four buildings named once each", "4 buildings",
         "The 2025 lease book names AM, Taft, Semple and Taft/semple once "
         "each. The other twenty-two tenants are in YBI or TBB5.",
         "Are these YBI buildings, and are Taft, Semple and Taft/semple two "
         "buildings or three?",
         "Square footage per building is what sizes the facilities carve-out."),

    Item("3.2", "Space", "One tenant across two buildings", "1 tenancy",
         "Taft/semple is a single row in the lease book.",
         "Which building does it belong to, or how should the square footage "
         "split between the two?",
         "A tenancy in no building cannot be carved out of the pool."),

    Item("3.3", "Space", "Eight tenancies with no start date", "18,592.56",
         "Azanna Elise, Equipment Appraisal Services, Greg Babinack, JSO "
         "Technologies, M. Jones, Made by Morgan, Parallax and Ralph Zerbonia "
         "say 'monthly' where a start date belongs.",
         "Month-to-month arrangements, or start dates that were never "
         "recorded?",
         "A suite occupied for part of the year is a part of a suite of cost."),

    Item("3.4", "Space", "MVMC starts 1 April 2026", "1 lease",
         "It is in the 2025 lease book and contributes no 2025 rent.",
         "Should it be in the 2025 book at all?",
         "A future tenancy counted as 2025 space overstates occupied area."),

    Item("4.1", "People", "The payroll register keys people by surname",
         "43 people",
         "EWING, RUBY, GAFFNEY. The register carries surnames and no payroll "
         "identifier.",
         "Any duplicate surnames on the 2025 register?",
         "If yes, two people's hours are already joined together and every "
         "effort figure for both is wrong. It would be a change to the "
         "ingest, not to a form."),

    Item("5.1", "Invoices", "The invoice dates on file are ours, not YBI's",
         "3 invoices",
         "10018, 10023 and 10039 all carry 2026-05-01 with an April 2026 "
         "service period, sitting in period 2025. Those dates are a "
         "placeholder in our loader — the line items and totals are real, the "
         "dates were never supplied.",
         "The real invoice dates and service periods for the three.",
         "A restatement is measured per invoice within a period, so a wrong "
         "date puts a claim in the wrong year."),

    Item("5.2", "Invoices", "No cash recorded against any invoice",
         "57,961.42",
         "37,593.90 + 1,374.00 + 18,993.52 issued, and zero receipts on the "
         "record.",
         "Have these been paid, in whole or in part?",
         "Collections are unknowable from the system today. A receipt may be "
         "negative, so a clawback would show here too."),

    Item("5.3", "Invoices", "The full invoice register does not exist",
         "4 objectives",
         "The system holds three invoices — 10018, 10023 and 10039, 57,961.42 "
         "between them. The 2025 ledger recognises America Makes revenue on "
         "four objectives: Drive AM 579,240.87, Digital Engineering "
         "579,074.25, Last Tactical Mile 368,222.24 and Hybrid 191,638.05 — "
         "1,718,175.41 in all.",
         "Every invoice issued to NCDMM in 2025, across all four objectives.",
         "A restatement is measured per invoice. With three on file the "
         "exercise can be demonstrated and not completed, and invoiced "
         "against recognised cannot be reconciled at all."),

    Item("6.1", "Agreements",
         "Six provisions cite a clause the agreement does not contain",
         "6 of 36",
         "Hybrid Phase 2 and Last Tactical Mile each carry Payment terms "
         "cited to §26 Payment, Invoicing frequency cited to §25 Invoicing, "
         "and Indirect provision cited to Attachment 3. Neither agreement "
         "contains a §25, a §26 or an Attachment 3 — both are "
         "ARTICLE-numbered instruments with no numbered clause headings "
         "anywhere — and neither contains the phrase \u201cNet 30\u201d or "
         "\u201cfifth business day\u201d. Those are ICAM\u2019s clauses; "
         "ICAM is the numbered NCDMM Subrecipient Agreement template and its "
         "ten provisions all check out against it. "
         "v_award_citation_check names the six.",
         "What do Hybrid\u2019s and LTM\u2019s agreements actually say about "
         "payment terms, invoicing frequency and indirect? If the substance "
         "is right but came from somewhere else \u2014 a flow-down, a "
         "purchase order, the prime \u2014 which document and which clause?",
         "The indirect provision is the one that matters. Schedule B says "
         "Hybrid budgets no indirect at all against 449,043 of labour and LTM "
         "budgets 81,772.76, while the register asserts \u201c10% of ODCs "
         "only\u201d on both. That is the restatement\u2019s central claim "
         "resting, in two places, on a sentence copied from the one agreement "
         "it was true of. A citation to a clause that does not exist is also "
         "the kind of thing a sponsor finds rather than a control."),

    Item("6.2", "Agreements",
         "Nobody has read the Drive AM agreement",
         "36 pages, 0 words",
         "The executed Drive AM subrecipient agreement on file is thirty-six "
         "pages of image with no text layer. Its eight recorded provisions "
         "\u2014 including the 1,103,594 total obligation at \u00a74.3, the "
         "\u00a711.11 precedence rule and \u201cnone budgeted\u201d for "
         "indirect \u2014 cannot be checked against it by anybody working "
         "from the file.",
         "Confirm the eight provisions against the paper agreement, and "
         "whether a text-bearing copy exists \u2014 a Word original, or the "
         "copy NCDMM holds.",
         "Drive AM is the largest America Makes award and the one whose "
         "Schedule B carries no indirect line at all against 583,594 of "
         "labour. That absence is the strongest evidence the restatement has, "
         "and at present it rests on a reading nobody can reproduce from the "
         "document on file."),
)
