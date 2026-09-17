/* What each kind of outstanding work is, in one place.
 *
 * There were three of these maps — Worklist.jsx, Dashboard.jsx and Home.jsx —
 * and each was missing different kinds, so the same item read as "Stale
 * decision" on one screen and as `STALE_CERTIFICATION` on another. Two of the
 * kinds the views emit were in none of them.
 *
 * Every map falls back to the raw database name, which is why nobody noticed:
 * the screen does not break, it just starts speaking SQL. This is the same
 * rule as coverage being defined once in the schema, and as the review script
 * deriving what each screen calls from App.jsx rather than keeping a list.
 *
 * `title` is one item. `plural` is a group of them, because the landing page
 * counts and the work list enumerates, and "Unclassified cost" and "Cost to
 * classify" are not interchangeable sentences. `to` is where it is actually
 * resolved — null only where there is genuinely nowhere yet, which is a gap
 * to close rather than a label to write.
 *
 * tests/test_worklist_labels.py reads the kinds out of the migrations and
 * fails if one has no entry here.
 */
export const KINDS = {
  UNCLASSIFIED: {
    title: "Unclassified cost",
    plural: "Cost to classify",
    short: "In P&L scope, with no live decision",
    why: "In P&L scope with no live decision. Unclassified cost is never defaulted into a pool, so the rate reads high while this list is long — the honest direction to err.",
    where: "Resolved in Classify.",
    to: "/classify",
  },
  POSITION_UNCONFIRMED: {
    title: "Working position",
    plural: "Positions nobody has adopted",
    short: "A script proposed it; it is not yet a judgment",
    why: "Proposed by the classification log and recorded under the controller's credentials, which is how a script writes honestly and is not the same claim as a person having judged it. Adopting it moves no figure — the rate is the same before and after — so this is about whose judgment the record says it is, and nothing else.",
    where: "Adopted in Classify \u203a Review.",
    to: "/classify/review",
  },
  PARTY_UNDETERMINED: {
    title: "Party with no 200.331 determination",
    plural: "Parties with no 200.331 determination",
    short: "Contractor or subrecipient is unanswered",
    why: "2 CFR 200.1 takes the first $25,000 of a subaward into MTDC and a contract for services whole, so the part of this payment above the cap is in the base or out of it depending on a 200.331 determination nobody has made. The substance of the relationship governs and not the form \u2014 every one of these is booked as CONSULTANT, which settles nothing. UNDETERMINED is NO DATA and never a pass: while it stands the payment sits in MTDC whole, which is the contractor answer applied by omission.",
    where: "Answered in Classify \u203a Parties.",
    to: "/classify/parties",
  },
  RECOMMENDATION_OPEN: {
    title: "Recommendation to answer",
    plural: "Recommendations to answer",
    short: "Somebody has proposed a change",
    why: "Somebody who may read the cost record has proposed a change — to a classification, to a building's area, to what a space is used for, or to who paid for an asset — with a reason. It writes nothing: accepting it records the change through the ordinary route for that register, under the controller's name, citing the recommendation.",
    where: "Answered in Classify \u203a Review.",
    to: "/classify/review",
  },
  BLOCKS_SEAL: {
    title: "Blocks the seal",
    plural: "Judgments that block the seal",
    short: "Graded unsupported or test assumption",
    why: "Decided, but graded unsupported or test assumption. A locked foundation may not carry either, so these prevent a rate from being sealed.",
    where: "Raise the grade in Classify once evidence exists.",
    to: "/classify",
  },
  STALE_DECISION: {
    title: "Stale decision",
    plural: "Stale decisions",
    short: "The line moved underneath the judgment",
    why: "The source line changed after the decision was made. The judgment may still be right, but it was made about different numbers.",
    where: "Re-decide in Classify.",
    to: "/classify",
  },
  NEEDS_EVIDENCE: {
    title: "Needs evidence",
    plural: "Judgments with no document",
    short: "Federally chargeable, nothing cited",
    why: "Federally allowable or pending, with no document cited on the judgment. Attaching a document is not the same as citing it — the gate reads the citation.",
    where: "Attach and cite in Classify.",
    to: "/classify",
  },
  NEEDS_CERTIFICATION: {
    title: "Needs certification",
    plural: "Effort not yet certified",
    short: "Only the person whose effort it was can sign",
    why: "Effort distribution not attested by the employee or a supervisor with firsthand knowledge. 2 CFR 200.430(i) wants the person who did the work.",
    where: "The chase list is in Contracts → People. A manager cannot sign on somebody's behalf, so it is a list to go and ask.",
    to: "/contracts/people",
  },
  STALE_CERTIFICATION: {
    title: "Certification out of date",
    plural: "Certifications overtaken by the record",
    short: "Signed, then the distribution changed underneath it",
    why: "The person signed, and the effort distribution moved afterwards. What they attested to is no longer what the record says, so the signature covers different figures from the ones in the rate.",
    where: "Ask them to sign again in Contracts → People.",
    to: "/contracts/people",
  },
  EMPLOYMENT_UNKNOWN: {
    title: "Employment terms missing",
    plural: "Employment terms missing",
    short: "No weekly hours to measure a timesheet against",
    why: "No status, weekly hours or start date on file. Expected hours are the denominator every effort percentage is measured against — twenty hours a week is the whole of a half-time job and half of a full-time one, and nothing on the record says which.",
    where: "Issue the roster workbook in Requests, or record the terms directly.",
    to: "/requests",
  },
  SPACE_UNMEASURED: {
    title: "Square footage not on file",
    plural: "Square footage not on file",
    short: "The facilities carve-out is sized by area",
    why: "No building has usable area recorded. The 2 CFR 200.465 carve-out is sized by area, so occupancy cost cannot be split between the programme and the tenants at all.",
    where: "Issue the space workbook in Requests, or measure it in Facilities.",
    to: "/space",
  },
  SPACE_UNATTRIBUTED: {
    title: "Space with nobody in it",
    plural: "Space nobody is standing in",
    short: "Measured, but not accounted for in full",
    why: "The building is measured and its space units do not account for it in full. Area is not a driver until somebody is standing in it, and a building that does not add up drops out of the occupancy view entirely — every dollar of its cost then reaches the federal pool unchallenged.",
    where: "Record the remaining units in Facilities.",
    to: "/space",
  },
  ASSET_FUNDING_UNKNOWN: {
    title: "Asset funding unknown",
    plural: "Assets with no funding source",
    short: "Depreciation reads as fully allowable",
    why: "No funding source recorded, so depreciation currently reads as fully allowable. That is the optimistic reading and 2 CFR 200.436(b) disallows the federally funded share.",
    where: "Issue the asset register workbook in Requests — it goes out pre-filled from YBI's own schedule, and asks only for the column it does not carry.",
    to: "/requests",
  },
  DONATION_RATE_MISSING: {
    title: "Donated time with no rate",
    plural: "Donated time with no rate",
    short: "Hours on the record, no documented valuation",
    why: "Donated hours are recorded against an objective with no documented hourly rate, so they cannot be valued. A rate chosen later, once the effect on the total is visible, is not a valuation — which is why the basis is required and why nobody sets it on their own hours.",
    where: "Set the rate in Timesheet, under Donated time. Not on your own hours — 2 CFR 200.306(e) wants a rate consistent with what YBI pays for similar work, and that is a judgment about your time rather than yours to make.",
    to: "/timesheet",
  },
  CHARGE_CODE_UNASSIGNED: {
    title: "Code with nobody assigned",
    plural: "Codes with nobody assigned",
    short: "Hours booked that nobody authorised",
    why: "Hours have been booked to a code with an empty assignment list. The gate turns on for a code as soon as one person is assigned to it, so an empty list is not a refusal — it is a code that predates the mechanism.",
    where: "Assign the people who work on it in Contracts → Codes.",
    to: "/contracts/codes",
  },
  INVOICE_NO_INDIRECT: {
    title: "Invoice without indirect",
    plural: "Invoices billing no indirect",
    short: "Recovery forgone on the face of it",
    why: "A cost-reimbursement invoice carrying no indirect line forgoes recovery outright, rather than under-recovering. The absence is itself the evidence — it is the record of what YBI was never budgeted to claim.",
    where: "Restatement is proposed in Awards.",
    to: "/awards",
  },
  INVOICE_NO_AWARD: {
    title: "Invoice without an award",
    plural: "Invoices with no award",
    short: "No ceiling to test against",
    why: "Not linked to an award, so there is no ceiling to test the claim against.",
    where: "Register the agreement in Awards.",
    to: "/awards",
  },
  AWARD_NO_CEILING: {
    title: "Award with no ceiling",
    plural: "Awards with no ceiling",
    short: "Nothing to cap a claim against",
    why: "A ceiling is read off a clause, not derived, so none of the cross-reference controls can catch a missing one. A restatement is capped against the ceiling, so an award without one cannot be measured at all.",
    where: "Read the obligation clause into the record in Awards.",
    to: "/awards",
  },
};

/** What a screen shows for a kind it has no entry for. Falling back to the
 *  raw database name is what hid two missing kinds for as long as it did. */
export const forKind = (kind) =>
  KINDS[kind] || { title: kind, plural: kind, short: "", why: "", where: "", to: null };
