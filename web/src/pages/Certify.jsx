import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Card, Empty, PageHead, Pill, Stat, Table } from "../components/ui.jsx";

const money = (v) =>
  v === null || v === undefined ? "—"
    : Number(v).toLocaleString(undefined, { minimumFractionDigits: 2,
                                            maximumFractionDigits: 2 });
const pct = (v) => `${(Number(v) * 100).toFixed(1)}%`;
const when = (t) => (!t ? "" : new Date(t).toLocaleString());

/* The employee's own screen. It shows the whole distribution — every activity,
   not the federally funded ones — because that is what the certification
   covers and what makes the percentages mean anything. */
export default function Certify() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [signed, setSigned] = useState(null);

  const load = () =>
    api.myCertification()
      .then((d) => { setData(d); setError(""); })
      .catch((e) => setError(String(e.message || e)));

  useEffect(() => { load(); }, []);

  async function sign() {
    setBusy(true);
    try {
      const r = await api.sign({ employee_key: data.employee_key,
                                 period: data.period, acknowledged: true });
      setSigned(r);
      await load();
    } catch (e) {
      setError(String(e.message || e));
    }
    setBusy(false);
  }

  if (error && !data) return <Empty mark="!" title="Not available">{error}</Empty>;
  if (!data) return <Empty mark="…" title="Loading" />;

  const rows = data.distribution || [];
  const status = data.status || {};
  const totalShare = rows.reduce((a, r) => a + Number(r.share), 0);

  return (
    <div className="dash">
      <PageHead
        title="Certify your effort"
        aside={
          <>
            {status.certified && !status.stale && (
              <Pill tone="good">Signed {when(status.signed_at)}</Pill>
            )}
            {status.certified && status.stale && (
              <Pill tone="fail">Signature is stale</Pill>
            )}
            {!status.certified && <Pill tone="fail">Not yet signed</Pill>}
          </>
        }>
        Period {data.period} · {data.employee_key}. The signature only you can
        give — 2 CFR 200.430(i) asks for the person whose effort it was.
      </PageHead>

      {status.stale && (
        <Card variant="raised">
          <p>
            Your distribution has changed since you signed it on{" "}
            {when(status.signed_at)}. The earlier signature attested to
            different numbers, so it no longer supports these. Please review and
            sign again.
          </p>
        </Card>
      )}

      <Card title="Your distribution" aside={`${rows.length} activities`}>
        {rows.length === 0 ? (
          <Empty mark="—" title="Nothing recorded for you in this period" />
        ) : (
          <>
            <div className="stat-row">
              <Stat label="Total compensation" size="lg"
                    value={money(rows[0]?.payroll_wages)} />
              <Stat label="Activities" value={rows.length} />
              <Stat label="Accounted for" value={pct(totalShare)}
                    tone={Math.abs(totalShare - 1) > 0.001 ? "fail" : undefined} />
            </div>
            <Table columns={[
              { label: "Activity", align: "left" }, { label: "Share" },
              { label: "Wages" }, { label: "Basis", align: "left" },
            ]}>
              {rows.map((r) => (
                <tr key={r.objective_id}>
                  <td className="l strong">{r.objective_id}</td>
                  <td className="num">{pct(r.share)}</td>
                  <td className="num">{money(r.distributed_wages)}</td>
                  <td className="l quiet small">
                    {r.is_reconstructed ? "reconstructed" : "as recorded"}
                  </td>
                </tr>
              ))}
            </Table>
          </>
        )}
      </Card>

      {rows.length > 0 && (
        <Card title="Certification" variant="raised">
          <p className="cert-statement">{data.statement}</p>

          {signed ? (
            <Pill tone="good">
              Signed {when(signed.signed_at)} · {signed.objectives} activities
            </Pill>
          ) : (
            <>
              <label className="cert-ack">
                <input type="checkbox" checked={ack}
                       onChange={(e) => setAck(e.target.checked)} />
                <span>
                  I have read the statement above and it is true to the best of
                  my knowledge.
                </span>
              </label>
              {error && <div className="signin-error" role="alert">{error}</div>}
              <button className="btn primary" disabled={!ack || busy}
                      onClick={sign}>
                {busy ? "Signing…" : "Sign certification"}
              </button>
              <p className="quiet small">
                Your name, the time, and the distribution exactly as it stands
                now are recorded together. If the distribution changes later,
                this signature is marked stale rather than quietly carried over.
              </p>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
