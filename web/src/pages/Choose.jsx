import React from "react";

/* Two products, one login.
 *
 * The application was one nav of twenty tabs doing two unrelated jobs: a
 * year being closed, and a company being run. Import, Reconcile, Classify,
 * Rates, Review and Restate are a 2025 audit that ends — the books arrive,
 * the cost is judged, a rate falls out, the federal invoices are reissued,
 * and then nobody touches it again. My time, Contracts, Projects, Inventory
 * and Space are an ongoing system with no end date. Putting them in one row
 * made both harder to read and neither easy to finish.
 *
 * So this stands in front, and it offers exactly two things. Not a
 * dashboard, not a summary, not a set of shortcuts — two doors, because a
 * third option on this screen would be a third thing to think about before
 * the first decision of the day.
 *
 * Two rules it keeps:
 *
 * It says what is *behind* each door rather than describing it. "Eleven
 * control points, 757 judgments, four rates" is a person deciding where to
 * go; "manage your financial data" is a brochure.
 *
 * And it is not a permission boundary. Everything behind both doors is
 * gated exactly as it was — this only decides which set of tabs the shell
 * draws, and the API refuses what it always refused.
 */

function Door({ mark, title, lede, points, cta, tone, onPick }) {
  return (
    <button className={`door ${tone}`} onClick={onPick}>
      <span className="door-mark" aria-hidden="true">{mark}</span>
      <span className="door-title">{title}</span>
      <span className="door-lede">{lede}</span>
      <ul className="door-points">
        {points.map((p) => <li key={p}>{p}</li>)}
      </ul>
      <span className="door-cta">{cta} &rarr;</span>
    </button>
  );
}

export default function Choose({ actor, onPick }) {
  const first = (actor.display_name || "").split(" ")[0];
  return (
    <div className="choose">
      <div className="choose-head">
        <h1>Good to see you, {first}.</h1>
        <p className="lede">
          Two pieces of work live here and they are not the same job. Pick the
          one you are doing; you can switch at any time from the top of the
          screen.
        </p>
      </div>

      <div className="door-row">
        <Door
          tone="audit"
          mark="Schedule A–G"
          title="2025 Audit"
          lede="The year being closed. The books, the judgments behind every
                cost, the indirect rate that falls out of them, and the
                America Makes invoices reissued on it."
          points={[
            "The general ledger, profit and loss and balance sheet, against each other",
            "Every cost judged, with the evidence and the reason on the record",
            "Fringe, overhead, G&A and the combined indirect rate",
            "The restatement, and the audit package that carries it",
          ]}
          cta="Open the audit"
          onPick={() => onPick("audit")}
        />

        <Door
          tone="fcs"
          mark="Ongoing"
          title="Financial Control Solution"
          lede="The company being run. Timesheets, charge codes, projects,
                inventory and space — the system that keeps the next year's
                cost right as it happens rather than reconstructing it."
          points={[
            "Timesheets and effort, recorded as the work is done",
            "Charge codes, projects and who may charge what",
            "The equipment register and the space book",
            "The 2026 chart, where classification becomes arithmetic",
          ]}
          cta="Open the system"
          onPick={() => onPick("fcs")}
        />
      </div>
    </div>
  );
}
