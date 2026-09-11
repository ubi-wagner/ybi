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
  changePassword: (body) =>
    req("/auth/password", { method: "POST", body: JSON.stringify(body) }),
  dashboard: (period) => req("/dashboard" + (period ? `?period=${period}` : "")),
  worklist: (params) => req("/dashboard/worklist?" + new URLSearchParams(params)),
  activity: (params) => req("/dashboard/activity?" + new URLSearchParams(params)),
  timesheetObjectives: (period = "2025") =>
    req(`/timesheet/objectives?period=${period}`),
  timesheetEntries: (params) => req("/timesheet/entries?" + new URLSearchParams(params)),
  timesheetSummary: (params) => req("/timesheet/summary?" + new URLSearchParams(params || {})),
  putTime: (body) => req("/timesheet/entry", { method: "POST", body: JSON.stringify(body) }),
  removeTime: (body) =>
    req("/timesheet/entry/remove", { method: "POST", body: JSON.stringify(body) }),
  timesheetRoster: (period = "2025") => req(`/timesheet/roster?period=${period}`),
  timesheetMonths: (params) => req("/timesheet/months?" + new URLSearchParams(params || {})),
  employment: (params) => req("/timesheet/employment?" + new URLSearchParams(params || {})),
  putEmployment: (body) =>
    req("/timesheet/employment", { method: "PUT", body: JSON.stringify(body) }),
  timesheetCoverage: (params) =>
    req("/timesheet/coverage?" + new URLSearchParams(params || {})),
  submitTimesheet: (body) =>
    req("/timesheet/submit", { method: "POST", body: JSON.stringify(body) }),
  withdrawTimesheet: (body) =>
    req("/timesheet/withdraw", { method: "POST", body: JSON.stringify(body) }),
  myCertification: () => req("/certify/mine"),
  sign: (body) => req("/certify/sign", { method: "POST", body: JSON.stringify(body) }),
  certificationStatus: () => req("/certify/status"),
  certificationFor: (key) => req(`/certify/${encodeURIComponent(key)}`),
  auditPackageUrl: (period = "2025") => `/api/export/audit-package?period=${period}`,

  // What this person owes, rather than what is outstanding in general.
  myWorklist: (period = "2025") => req(`/dashboard/worklist/mine?period=${period}`),

  // Contracts and charge codes — the income side.
  contracts: (period = "2025") => req(`/contracts?period=${period}`),
  contract: (id, period = "2025") => req(`/contracts/${encodeURIComponent(id)}?period=${period}`),
  chargeCodes: (period = "2025") => req(`/contracts/charge-codes?period=${period}`),
  chargeCodePeople: (id, period = "2025") =>
    req(`/contracts/charge-codes/${encodeURIComponent(id)}/people?period=${period}`),
  createChargeCode: (body, period = "2025") =>
    req(`/contracts/charge-codes?period=${period}`,
        { method: "POST", body: JSON.stringify(body) }),
  authoriseCharge: (id, body, period = "2025") =>
    req(`/contracts/charge-codes/${encodeURIComponent(id)}/authorise?period=${period}`,
        { method: "POST", body: JSON.stringify(body) }),
  revokeCharge: (id, body, period = "2025") =>
    req(`/contracts/charge-codes/${encodeURIComponent(id)}/revoke?period=${period}`,
        { method: "POST", body: JSON.stringify(body) }),
  putAwardTerm: (id, body) =>
    req(`/contracts/${encodeURIComponent(id)}/terms`,
        { method: "PUT", body: JSON.stringify(body) }),
  createMilestone: (id, body) =>
    req(`/contracts/${encodeURIComponent(id)}/milestones`,
        { method: "POST", body: JSON.stringify(body) }),
  setMilestoneState: (id, body) =>
    req(`/contracts/milestones/${encodeURIComponent(id)}/state`,
        { method: "POST", body: JSON.stringify(body) }),
  milestone: (id, period = "2025") =>
    req(`/contracts/milestones/${encodeURIComponent(id)}?period=${period}`),
  addReceipt: (invoiceId, body) =>
    req(`/contracts/invoices/${encodeURIComponent(invoiceId)}/receipts`,
        { method: "POST", body: JSON.stringify(body) }),
  chargingPeople: (period = "2025") => req(`/contracts/employees?period=${period}`),
  employeeCharging: (key, period = "2025") =>
    req(`/contracts/employees/${encodeURIComponent(key)}/charging?period=${period}`),

  // Final review — the three deliverables somebody signs. Each screen reads
  // the same endpoint its workbook is built from, so a figure on screen and
  // the same figure in the file cannot disagree.
  reviewRate: (period = "2025") => req(`/review/rate?period=${period}`),
  reviewForm990: (period = "2025") => req(`/review/form-990?period=${period}`),
  reviewAttachments: (period = "2025") => req(`/review/attachments?period=${period}`),
  auditorsReport: (period = "2025") => req(`/review/auditors-report?period=${period}`),
  rateBuildupUrl: (period = "2025") => `/api/export/rate-buildup?period=${period}`,
  auditorsReportUrl: (period = "2025") => `/api/export/auditors-report?period=${period}`,
  form990Url: (period = "2025") => `/api/export/form-990?period=${period}`,
  coverage: (period = "2025") => req(`/classify/coverage?period=${period}`),
  queue: (params) => req("/classify/queue?" + new URLSearchParams(params)),
  vocabulary: () => req("/classify/vocabulary"),
  undoable: (params) => req("/undo?" + new URLSearchParams(params || {})),
  undo: (body) => req("/undo", { method: "POST", body: JSON.stringify(body) }),
  advice: (groupKey, period = "2025") =>
    req(`/classify/advice?period=${period}&group_key=${encodeURIComponent(groupKey)}`),
  segment: (body) => req("/classify/segment", { method: "POST", body: JSON.stringify(body) }),
  segments: (period = "2025") => req(`/classify/segments?period=${period}`),
  decide: (body) => req("/classify/decide", { method: "POST", body: JSON.stringify(body) }),
  lanes: (period = "2025") => req(`/lanes?period=${period}`),
  createLane: (body) => req("/lanes", { method: "POST", body: JSON.stringify(body) }),
  laneBuildup: (id) => req(`/lanes/${id}/buildup`),
  rates: (period = "2025") => req(`/rates/current?period=${period}`),
  seal: (body) => req("/rates/seal", { method: "POST", body: JSON.stringify(body) }),
  imports: (period = "2025") => req(`/imports?period=${period}`),
  evidenceCoverage: (period = "2025") => req(`/evidence/coverage?period=${period}`),
  evidenceRegister: (period = "2025") => req(`/evidence?period=${period}`),
  evidenceForGroup: (groupKey, period = "2025") =>
    req(`/evidence/group?period=${period}&group_key=${encodeURIComponent(groupKey)}`),
  evidenceFor: (targetType, targetId) =>
    req("/evidence/for?" + new URLSearchParams({ target_type: targetType,
                                                 target_id: targetId })),
  evidenceFileUrl: (id) => `/api/evidence/${encodeURIComponent(id)}/file`,
  addNote: (body) => req("/evidence/note", { method: "POST", body: JSON.stringify(body) }),
  /* Multipart, so it cannot go through req(): setting Content-Type by hand
     drops the boundary the browser generates and the server sees no file. */
  uploadEvidence: async (form) => {
    const res = await fetch("/api/evidence/upload",
                            { method: "POST", credentials: "same-origin", body: form });
    if (res.status === 401) throw new Unauthorized("Not signed in");
    if (res.status === 403) throw new Forbidden(await res.text());
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    return res.json();
  },
  facilities: (period = "2025") => req(`/facilities?period=${period}`),
  putFacility: (body) => req("/facilities", { method: "PUT", body: JSON.stringify(body) }),
  spaceUnits: (params) => req("/facilities/space?" + new URLSearchParams(params || {})),
  putSpaceUnit: (body) =>
    req("/facilities/space", { method: "PUT", body: JSON.stringify(body) }),
  equipment: (period = "2025") => req(`/facilities/equipment?period=${period}`),
  putEquipmentUse: (body) =>
    req("/facilities/equipment/use", { method: "POST", body: JSON.stringify(body) }),
  inKind: (period = "2025") => req(`/facilities/in-kind?period=${period}`),
  putInKind: (body) =>
    req("/facilities/in-kind", { method: "POST", body: JSON.stringify(body) }),
  awards: () => req("/awards"),
  chartSummary: () => req("/chart/summary"),
  chartAccounts: () => req("/chart/accounts"),
  chartCrosswalk: (period = "2025") => req(`/chart/crosswalk?period=${period}`),
  reconcile: (period = "2025") => req(`/reconcile?period=${period}`),
  reconcileGlPl: (period = "2025") => req(`/reconcile/gl-pl?period=${period}`),
  reconcileGlBs: (period = "2025") => req(`/reconcile/gl-bs?period=${period}`),
  reconcileItems: (period = "2025") => req(`/reconcile/items?period=${period}`),
  reconcileAliases: (period = "2025") => req(`/reconcile/aliases?period=${period}`),
  reconcilePropose: (period = "2025") => req(`/reconcile/propose?period=${period}`),
  // People and access
  actors: () => req("/auth/actors"),
  rosterGaps: () => req("/auth/roster-gaps"),
  createActor: (body) =>
    req("/auth/actors", { method: "POST", body: JSON.stringify(body) }),
  grantPortfolio: (id, portfolio, reason) =>
    req(`/auth/actors/${id}/portfolios`,
        { method: "POST", body: JSON.stringify({ portfolio, reason }) }),
  revokePortfolio: (id, portfolio, reason) =>
    req(`/auth/actors/${id}/portfolios/revoke`,
        { method: "POST", body: JSON.stringify({ portfolio, reason }) }),
  setRecordAccess: (id, granted, reason) =>
    req(`/auth/actors/${id}/record-access`,
        { method: "POST", body: JSON.stringify({ granted, reason }) }),
  amendActor: (id, body) =>
    req(`/auth/actors/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  setActorActive: (id, is_active, reason) =>
    req(`/auth/actors/${id}/active`,
        { method: "POST", body: JSON.stringify({ is_active, reason }) }),
  resetActorPassword: (id, new_password) =>
    req(`/auth/actors/${id}/password`,
        { method: "POST", body: JSON.stringify({ new_password }) }),

  // My documents — the module everybody gets
  myDocuments: () => req("/documents/mine"),
  uploadDocument: async (form) => {
    const res = await fetch("/api/documents/upload",
                            { method: "POST", credentials: "same-origin", body: form });
    if (res.status === 401) throw new Unauthorized("Not signed in");
    if (res.status === 403) throw new Forbidden(await res.text());
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    return res.json();
  },
  documentInbox: (period = "2025") =>
    req(`/documents/inbox?period=${period}`),

  /* The library — everything, for anyone who may read the cost record.
     The two URL helpers are not fetches: a <iframe> and a download both want
     a URL the browser goes to itself, carrying the session cookie, so the
     bytes never pass through JavaScript on the way to the screen. */
  documentLibrary: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null));
    const s = q.toString();
    return req(`/documents/library${s ? `?${s}` : ""}`);
  },
  /* Reports — the two documents the reconciliation needs on paper.
     Both are URLs the browser goes to itself so the bytes never pass
     through JavaScript, same as the library. */
  invoicesToRender: (period = "") =>
    req(`/reports/invoices${period ? `?period=${period}` : ""}`),
  invoicePdfUrl: (id) => `/api/reports/invoice/${encodeURIComponent(id)}`,
  fileInvoice: (id) =>
    req(`/reports/invoice/${encodeURIComponent(id)}/file`, { method: "POST" }),
  timesheetReportUrl: (period = "", employeeKey = "") => {
    const q = new URLSearchParams();
    if (period) q.set("period", period);
    if (employeeKey) q.set("employee_key", employeeKey);
    const s = q.toString();
    return `/api/reports/timesheet${s ? `?${s}` : ""}`;
  },

  documentViewUrl: (id) =>
    `/api/documents/${encodeURIComponent(id)}/file?inline=1`,
  documentDownloadUrl: (id) =>
    `/api/documents/${encodeURIComponent(id)}/file`,
  attachDocument: (body) =>
    req("/documents/attach", { method: "POST", body: JSON.stringify(body) }),

  addReconcilingItem: (body) =>
    req("/reconcile/items", { method: "POST", body: JSON.stringify(body) }),
  retractReconcilingItem: (id, reason) =>
    req(`/reconcile/items/${id}/retract`, { method: "POST", body: JSON.stringify({ reason }) }),
};

export const money = (n) => {
  const v = Number(n || 0);
  return (v < 0 ? "(" : "") +
    Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 }) +
    (v < 0 ? ")" : "");
};
