const base = "/api";

/* A 401 is not a failure to report, it is a state to move to. Throwing a
   generic Error made every screen render "401: Not signed in" as though the
   server were broken. Unauthorized carries the signal instead, and the shell
   sends the user to the sign-in screen. */
export class Unauthorized extends Error {}
export class Forbidden extends Error {}

async function req(path, opts = {}) {
  const res = await fetch(base + path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (res.status === 401) throw new Unauthorized("Not signed in");
  if (res.status === 403) {
    const body = await res.text();
    throw new Forbidden(body);
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  health: () => req("/health"),
  me: () => req("/auth/me"),
  login: (email, password) =>
    req("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => req("/auth/logout", { method: "POST" }),
  dashboard: (period) => req("/dashboard" + (period ? `?period=${period}` : "")),
  worklist: (params) => req("/dashboard/worklist?" + new URLSearchParams(params)),
  activity: (params) => req("/dashboard/activity?" + new URLSearchParams(params)),
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
