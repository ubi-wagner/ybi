import React from "react";

/* Cost pools have one visual identity across every screen. Abbreviation always
   travels with the colour — a reviewer printing to greyscale, or anyone with a
   colour vision deficiency, still reads the pool. */

export const POOLS = {
  DIRECT:        { cls: "p-DIRECT",      abbr: "DIR", label: "Direct" },
  FRINGE:        { cls: "p-FRINGE",      abbr: "FRG", label: "Fringe" },
  OVERHEAD:      { cls: "p-OVERHEAD",    abbr: "FAC", label: "Facilities" },
  "G&A":         { cls: "p-GA",          abbr: "G&A", label: "General & admin" },
  RENTAL_DIRECT: { cls: "p-RENTAL",      abbr: "RNT", label: "Rental direct" },
  FUNDRAISING:   { cls: "p-FUNDRAISING", abbr: "FUN", label: "Fundraising" },
  UNALLOWABLE:   { cls: "p-UNALLOWABLE", abbr: "UNA", label: "Unallowable" },
  EXCLUDED:      { cls: "p-EXCLUDED",    abbr: "EXC", label: "Excluded" },
};

const NONE = { cls: "p-NONE", abbr: "—", label: "Not yet classified" };

export function PoolChip({ pool, objective }) {
  const p = POOLS[pool] || NONE;
  return (
    <span className={`pool-chip ${p.cls}`} title={p.label}>
      <span className="abbr">{p.abbr}</span>
      {objective ? <span>{objective}</span> : null}
    </span>
  );
}

/* Row stripe. Spread onto <tr>: <tr {...poolRow(r.pool)}> */
export function poolRow(pool) {
  const key = (POOLS[pool] || NONE).cls.replace("p-", "").toLowerCase();
  const map = { direct: "direct", fringe: "fringe", overhead: "overhead", ga: "ga",
                rental: "rental", fundraising: "fundraising",
                unallowable: "unallowable", excluded: "excluded", none: "none" };
  return { className: "pool", style: { "--stripe": `var(--pool-${map[key] || "none"})` } };
}

export function PoolLegend({ counts = {} }) {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
      {Object.keys(POOLS).map((k) => (
        <span key={k} className={`pool-chip ${POOLS[k].cls}`}>
          <span className="abbr">{POOLS[k].abbr}</span>
          <span>{POOLS[k].label}</span>
          {counts[k] != null && <strong>{counts[k]}</strong>}
        </span>
      ))}
    </div>
  );
}
