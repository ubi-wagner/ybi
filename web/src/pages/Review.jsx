import React, { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { PageHead, Segmented } from "../components/ui.jsx";
import RateReview from "./RateReview.jsx";
import Form990 from "./Form990.jsx";
import Auditor from "./Auditor.jsx";

/* Final review — the three things that leave the building.
 *
 * One tab rather than three. They are read together: a reviewer checks the
 * rate, then the functional allocation it feeds, then the report that carries
 * both, and three separate destinations in a nav that already holds fourteen
 * makes that one journey look like three errands.
 *
 * Each pane is its own component and its own URL, so a link to the rate
 * build-up still lands on the rate build-up. */

const PANES = [
  ["report", "Auditor's report"],
  ["rate", "Indirect rate"],
  ["form-990", "Form 990"],
];

export default function Review({ actor }) {
  const { pane } = useParams();
  const nav = useNavigate();
  const current = PANES.some(([v]) => v === pane) ? pane : "report";

  return (
    <div className="page">
      <PageHead title="Final review" schedule="A-1"
                aside={<Segmented options={PANES} value={current}
                                  onChange={(v) => nav(`/review/${v}`)} />}>
        The three deliverables, each read from the same endpoint its workbook
        is built from — so a figure on the screen and the same figure in the
        file cannot disagree.
      </PageHead>

      {current === "report" && <Auditor embedded />}
      {current === "rate" && <RateReview embedded actor={actor} />}
      {current === "form-990" && <Form990 embedded />}
    </div>
  );
}
