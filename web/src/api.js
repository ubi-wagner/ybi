const base = "/api";

async function req(path, opts = {}) {
  const res = await fetch(base + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  health: () => req("/health"),
  coverage: (period = "2025") => req(`/classify/coverage?period=${period}`),
  queue: (params) => req("/classify/queue?" + new URLSearchParams(params)),
  vocabulary: () => req("/classify/vocabulary"),
  decide: (body) => req("/classify/decide", { method: "POST", body: JSON.stringify(body) }),
  lanes: (period = "2025") => req(`/lanes?period=${period}`),
  createLane: (body) => req("/lanes", { method: "POST", body: JSON.stringify(body) }),
  laneBuildup: (id) => req(`/lanes/${id}/buildup`),
  rates: (period = "2025") => req(`/rates/current?period=${period}`),
  seal: (body) => req("/rates/seal", { method: "POST", body: JSON.stringify(body) }),
  imports: (period = "2025") => req(`/imports?period=${period}`),
  evidenceCoverage: (period = "2025") => req(`/evidence/coverage?period=${period}`),
  awards: () => req("/awards"),
  chartSummary: () => req("/chart/summary"),
  chartAccounts: () => req("/chart/accounts"),
  chartCrosswalk: (period = "2025") => req(`/chart/crosswalk?period=${period}`),
};

export const money = (n) => {
  const v = Number(n || 0);
  return (v < 0 ? "(" : "") +
    Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 }) +
    (v < 0 ? ")" : "");
};
