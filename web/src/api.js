const base = "/api";

/* A 401 is not a failure to report, it is a state to move to. Throwing a
   generic Error made every screen render "401: Not signed in" as though the
   server were broken. Unauthorized carries the signal instead, and the shell
   sends the user to the sign-in screen. */
export class Unauthorized extends Error {}
export class Forbidden extends Error {}

/* Every request that fails, kept where the shell can show it.
 *
 * Thirty-two places load data with `.catch(() => {})`, which renders an empty
 * screen when the truth is that the request failed. "Nothing yet" and "the
 * server said no" look identical, and the person is left to guess — which is
 * the whole complaint this exists to answer.
 *
 * Fixing thirty-two call sites would work until the thirty-third was written.
 * This sits under all of them: a failure is recorded here whatever the caller
 * then does with it, so nothing can be swallowed by forgetting. Toasts still
 * carry the immediate message at the sites that catch; this is the net under
 * them. */
const failures = [];
const listeners = new Set();

export function onFailure(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
export const recentFailures = () => failures.slice();
export function clearFailures() {
  failures.length = 0;
  listeners.forEach((fn) => fn(failures));
}

function noteFailure(entry) {
  // Newest first, and bounded: a server that is down produces one failure per
  // poll, and an unbounded list would grow until the tab died.
  failures.unshift({ ...entry, at: new Date() });
  if (failures.length > 50) failures.length = 50;
  listeners.forEach((fn) => fn(failures));
}

async function req(path, opts = {}) {
  const method = opts.method || "GET";
  let res;
  try {
    res = await fetch(base + path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
  } catch (e) {
    // The request never arrived. Distinct from any status, and the one case
    // where the server has no idea anything was attempted.
    noteFailure({ path, method, status: 0,
                  message: "The server could not be reached." });
    throw new Error(`Could not reach the server: ${e.message}`);
  }
  /* A 401 is a state to move to, not a failure to report. Recording it would
     fill the list every time a session expires, and the shell already sends
     the person to sign in. */
  if (res.status === 401) throw new Unauthorized("Not signed in");
  if (res.status === 403) {
    const body = await res.text();
    noteFailure({ path, method, status: 403, message: detailOf(body) });
    throw new Forbidden(body);
  }
  if (!res.ok) {
    const body = await res.text();
    noteFailure({ path, method, status: res.status, message: detailOf(body) });
    throw new Error(`${res.status}: ${detailOf(body)}`);
  }
  return res.status === 204 ? null : res.json();
}

/* Multipart, which cannot go through req(): setting Content-Type by hand
   drops the boundary the browser generates and the server sees no file. So
   the headers differ and *nothing else does* — same statuses, same sentence,
   and the same record taken underneath.

   The three upload helpers used to check `res.ok` and stop there, so an
   upload that failed threw a sentence the screen might catch and left no
   trace on the failure list at all. `FailureBell` exists to surface what the
   screens swallow, and it could not see an upload. */
async function sendForm(path, form, opts = {}) {
  const method = opts.method || "POST";
  let res;
  try {
    res = await fetch(base + path,
                      { method, credentials: "same-origin", body: form });
  } catch (e) {
    noteFailure({ path, method, status: 0,
                  message: "The server could not be reached." });
    throw new Error(`Could not reach the server: ${e.message}`);
  }
  if (res.status === 401) throw new Unauthorized("Not signed in");
  if (res.status === 403) {
    const body = await res.text();
    noteFailure({ path, method, status: 403, message: detailOf(body) });
    throw new Forbidden(body);
  }
  if (!res.ok) {
    const body = await res.text();
    noteFailure({ path, method, status: res.status, message: detailOf(body) });
    throw new Error(`${res.status}: ${detailOf(body)}`);
  }
  return res.status === 204 ? null : res.json();
}

/* The sentence the API gave, not the JSON it gave it in. A person reading
   `{"detail":"..."}` in a toast is reading our plumbing. */
/* The sentence inside an error, for the two screens that show one.
 *
 * `req` throws three shapes — a Forbidden carrying the raw body, an Error
 * whose message is "409: …", and a plain Error for a network failure — and
 * a screen that unpicked them itself would be a second copy of this
 * function, free to disagree with the first about what the server said.
 */
export function explain(err) {
  if (!err) return "";
  const raw = String(err.message ?? err);
  if (err instanceof Forbidden) return detailOf(raw);
  const numbered = raw.match(/^\d{3}: ([\s\S]+)$/);
  return numbered ? numbered[1] : raw;
}

function detailOf(body) {
  try {
    const parsed = JSON.parse(body);
    const d = parsed?.detail ?? parsed?.message ?? parsed?.error;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d[0]?.msg) {
      return d.map((x) => `${(x.loc || []).slice(1).join(".")}: ${x.msg}`)
              .join("; ");
    }
    /* A structured refusal carries its sentence in `message`; the rest of
       the object is for the screen to act on, not for a person to read.
       Without this the seal, the reconciliation and the stale-queue
       refusals all arrived in a toast as raw JSON. */
    if (d && typeof d.message === "string") return d.message;
    if (d) return JSON.stringify(d);
  } catch { /* not JSON; the body itself is the message */ }
  return (body || "").slice(0, 300);
}

export const api = {
  health: () => req("/health"),
  me: () => req("/auth/me"),
  login: (email, password) =>
    req("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => req("/auth/logout", { method: "POST" }),
  changePassword: (body) =>
    req("/auth/password", { method: "POST", body: JSON.stringify(body) }),
  /* `product` scopes the rollup to the job being done. Omitted is
     unfiltered, which is what a script reading the whole list expects. */
  dashboard: (period, product = "") =>
    req("/dashboard" + (period || product
      ? "?" + new URLSearchParams({ ...(period && { period }),
                                    ...(product && { product }) })
      : "")),
  /* The walk: the ten steps of the 2025 audit and where each one stands.
     Read, never computed — `v_audit_walk` owns it. */
  walk: (period = "2025") =>
    req(`/dashboard/walk?period=${encodeURIComponent(period)}`),
  /* The one fact every output reads: does the rate carry a signature.
     Certifying blocks nothing — it decides whether the paper says so. */
  certification: (period = "2025") =>
    req(`/rates/certification?period=${encodeURIComponent(period)}`),
  certify: (signature, note = "", period = "2025") =>
    req(`/rates/certify?period=${encodeURIComponent(period)}`,
        { method: "POST", body: JSON.stringify({ signature, note }) }),
  withdrawCertification: (reason, period = "2025") =>
    req(`/rates/certify/withdraw?period=${encodeURIComponent(period)}`,
        { method: "POST", body: JSON.stringify({ reason }) }),
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
  /* Hours given rather than paid, and what each is worth. Reading is open —
     somebody who gave a day should be able to see it was recorded and what
     it was put at. Setting the rate is the controller's, and never for
     their own hours: 2 CFR 200.306(e). */
  donations: (period = "2025") => req(`/timesheet/donations?period=${period}`),
  putDonationRate: (body) =>
    req("/timesheet/donation-rate", { method: "PUT", body: JSON.stringify(body) }),
  putEmployment: (body) =>
    req("/timesheet/employment", { method: "PUT", body: JSON.stringify(body) }),
  timesheetCoverage: (params) =>
    req("/timesheet/coverage?" + new URLSearchParams(params || {})),
  /* The controller's reconstruction, shown to the person whose work it was.
     A proposal, in the same sense every other proposal here is one: nothing
     is on the sheet until they adopt it. */
  timesheetDraft: (period = "2025") =>
    req(`/timesheet/draft?period=${period}`),
  adoptDraft: (body) =>
    req("/timesheet/adopt", { method: "POST", body: JSON.stringify(body) }),
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
  /* `product` scopes the list to the job being done — the audit or the
     ongoing system. Omitted means unfiltered, which is what a script reading
     the whole list expects. */
  myWorklist: (period = "2025", product = "") =>
    req(`/dashboard/worklist/mine?period=${period}`
        + (product ? `&product=${product}` : "")),
  // A helper recommends; the controller verifies and seals. Raises a todo
  // against the outstanding item, never a row in the register it points at.
  recommend: (body, period = "2025") =>
    req(`/dashboard/worklist/recommend?period=${period}`,
        { method: "POST", body: JSON.stringify(body) }),

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
  // Whether everything above ties to the financials. One row per report
  // and anchor, each read from the control that already owns its figure.
  reportTies: (period = "2025") => req(`/review/ties?period=${period}`),
  rateBuildupUrl: (period = "2025") => `/api/export/rate-buildup?period=${period}`,
  auditorsReportUrl: (period = "2025") => `/api/export/auditors-report?period=${period}`,
  form990Url: (period = "2025") => `/api/export/form-990?period=${period}`,
  coverage: (period = "2025") => req(`/classify/coverage?period=${period}`),
  /* The whole book, and the three sheets it divides into. Both read views
     and compute nothing — the screen that shows "100% of the general ledger"
     has to be able to prove it against the ledger, not assert it. */
  partitions: (period = "2025") =>
    req(`/classify/partitions?period=${encodeURIComponent(period)}`),
  glAccounted: (period = "2025") =>
    req(`/classify/ledger?period=${encodeURIComponent(period)}`),
  queue: (params) => req("/classify/queue?" + new URLSearchParams(params)),
  vocabulary: () => req("/classify/vocabulary"),
  undoable: (params) => req("/undo?" + new URLSearchParams(params || {})),
  undo: (body) => req("/undo", { method: "POST", body: JSON.stringify(body) }),
  advice: (groupKey, period = "2025") =>
    req(`/classify/advice?period=${period}&group_key=${encodeURIComponent(groupKey)}`),
  segment: (body) => req("/classify/segment", { method: "POST", body: JSON.stringify(body) }),
  segments: (period = "2025") => req(`/classify/segments?period=${period}`),
  decide: (body) => req("/classify/decide", { method: "POST", body: JSON.stringify(body) }),
  projects: (period = "2025") => req(`/projects?period=${period}`),
  project: (id, period = "2025") => req(`/projects/${id}?period=${period}`),
  openProject: (body) =>
    req("/projects", { method: "POST", body: JSON.stringify(body) }),
  setProjectStatus: (id, body) =>
    req(`/projects/${id}/status`, { method: "POST", body: JSON.stringify(body) }),
  todos: (params = {}) => req("/todos?" + new URLSearchParams(params)),
  openTodo: (body) =>
    req("/todos", { method: "POST", body: JSON.stringify(body) }),
  changeTodo: (id, body) =>
    req(`/todos/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  todoCovering: (period = "2025") => req(`/todos/covering?period=${period}`),
  claims: (params = {}) => req("/claims?" + new URLSearchParams(params)),
  approveClaim: (id, body) =>
    req(`/projects/${id}/claims`, { method: "POST", body: JSON.stringify(body) }),
  queryClaim: (id, body) =>
    req(`/claims/${id}/query`, { method: "POST", body: JSON.stringify(body) }),
  claimInvoiced: (id, body) =>
    req(`/claims/${id}/invoiced`, { method: "POST", body: JSON.stringify(body) }),
  lanes: (period = "2025") => req(`/lanes?period=${period}`),
  createLane: (body) => req("/lanes", { method: "POST", body: JSON.stringify(body) }),
  laneBuildup: (id) => req(`/lanes/${id}/buildup`),
  laneOverrides: (id) => req(`/lanes/${id}/overrides`),
  addLaneOverride: (id, body) =>
    req(`/lanes/${id}/overrides`, { method: "POST", body: JSON.stringify(body) }),
  removeLaneOverride: (id, overrideId) =>
    req(`/lanes/${id}/overrides/${overrideId}`, { method: "DELETE" }),
  laneAssumptions: (id) => req(`/lanes/${id}/assumptions`),
  setLaneAssumption: (id, body) =>
    req(`/lanes/${id}/assumptions`, { method: "PUT", body: JSON.stringify(body) }),
  compareLanes: (ids, period = "2025") =>
    req(`/lanes/compare?lanes=${ids.join(",")}&period=${period}`),
  restateCandidates: (period = "2025") => req(`/restate/candidates?period=${period}`),
  restatements: (period = "2025") => req(`/restate?period=${period}`),
  restatement: (id) => req(`/restate/${id}`),
  restate: (body, period = "2025") =>
    req(`/restate?period=${period}`, { method: "POST", body: JSON.stringify(body) }),
  restateStatus: (id, body) =>
    req(`/restate/${id}/status`, { method: "POST", body: JSON.stringify(body) }),
  // The two papers a restated invoice cannot travel without. Links rather
  // than `req` calls, because a PDF opens in the page the way a document in
  // the library does — and a download link is a door too, which is what
  // `test_every_capability_has_a_door` had to learn.
  amendmentMemoUrl: (awardId, period = "2025") =>
    `/api/restate/award/${encodeURIComponent(awardId)}/memo?period=${period}`,
  acceptanceFormUrl: (awardId, period = "2025") =>
    `/api/restate/award/${encodeURIComponent(awardId)}/acceptance?period=${period}`,
  rates: (period = "2025") => req(`/rates/current?period=${period}`),
  seal: (body) => req("/rates/seal", { method: "POST", body: JSON.stringify(body) }),
  // The rate itself. `POST /api/rates/compute` was complete on the server and
  // named in a comment on Rates.jsx, and **nothing in the SPA had ever called
  // it** — so the one figure the whole engagement produces could only be made
  // by a script. The restatement's defect and the timesheet draft's, in the
  // place it costs most. Found by walking the runbook rather than by reading.
  //
  // `{}` is deliberately the whole body: every field on ComputeIn is a policy
  // with a default, and that body is the only one in this API that refuses an
  // unknown key. A screen inventing a field name here would be refused, which
  // is the behaviour that is wanted.
  // The way back. The runbook's own recovery step — "a judgment was wrong
  // after sealing: unseal with a written reason, which supersedes the rate"
  // — could not be performed in the application at all. The reason is a
  // query parameter because the route takes it as one; it is required, and
  // the handler refuses a blank.
  unseal: (reason, period = "2025") =>
    req(`/rates/unseal?period=${period}&reason=${encodeURIComponent(reason)}`,
        { method: "POST" }),
  // What the system refused, and what it said. `audit_log` means "this
  // changed", so by construction it says nothing when a change does not
  // happen; `refusal` is the other half, and nothing in the application
  // could read it.
  refusals: (limit = 50, mine = true) =>
    req(`/dashboard/refusals?limit=${limit}&mine=${mine}`),
  computeRate: (body = {}, period = "2025") =>
    req(`/rates/compute?period=${period}`,
        { method: "POST", body: JSON.stringify(body) }),
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
  uploadEvidence: (form) => sendForm("/evidence/upload", form),
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
  awardConstraints: (id) => req(`/awards/${id}/constraints`),
  awardTrueup: (id) => req(`/awards/${id}/trueup`),

  /* The import cycle. These four were the last raw `fetch()` calls in the
     SPA, and they were raw in the way that matters: no status check, so an
     import the server *refused* came back as `{detail: "..."}`, was read as
     a result, and the screen said "0 lines added to the ledger" in the tone
     it uses for success. A refusal is the one thing an import screen must
     never round to nothing happening. */
  importUpload: (file, report, period = "2025") => {
    const fd = new FormData();
    fd.append("file", file);
    return sendForm(`/imports/upload?report=${encodeURIComponent(report)}`
                    + `&period=${encodeURIComponent(period)}`, fd);
  },
  importParse: (batchId) => req(`/imports/${batchId}/parse`, { method: "POST" }),
  importPreview: (batchId) => req(`/imports/${batchId}/preview`),
  importAccept: (batchId) => req(`/imports/${batchId}/accept`, { method: "POST" }),
  chartSummary: () => req("/chart/summary"),
  chartAccounts: () => req("/chart/accounts"),
  chartCrosswalk: (period = "2025") => req(`/chart/crosswalk?period=${period}`),
  reconcile: (period = "2025") => req(`/reconcile?period=${period}`),
  reconcileGlPl: (period = "2025") => req(`/reconcile/gl-pl?period=${period}`),
  reconcileGlBs: (period = "2025") => req(`/reconcile/gl-bs?period=${period}`),
  reconcileItems: (period = "2025") => req(`/reconcile/items?period=${period}`),
  reconcilePayroll: (period = "2025") => req(`/reconcile/payroll?period=${period}`),
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
  uploadDocument: (form) => sendForm("/documents/upload", form),
  documentInbox: (period = "2025") =>
    req(`/documents/inbox?period=${period}`),

  /* The library — everything, for anyone who may read the cost record.
     The two URL helpers are not fetches: a <iframe> and a download both want
     a URL the browser goes to itself, carrying the session cookie, so the
     bytes never pass through JavaScript on the way to the screen. */
  // How much the documents in each family differ in *form*. The question
  // is whether the parsers survive next year's exports, and three of them
  // have already been caught by a second instance.
  documentVariability: () => req("/documents/variability"),
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

  /* The guidebook — the manuals and the generated PDFs, for anybody signed
     in. Not gated on reading the cost record: the everybody manual is
     written for somebody with a timesheet and no portfolio. */
  /* Open your own account. The password here is the organisation's, never
     one the applicant chose — they set theirs on the next screen, through
     the same gate everybody else meets. */
  register: (email, password, display_name = "") =>
    req("/auth/register", { method: "POST",
      body: JSON.stringify({ email, password, display_name }) }),

  guides: () => req("/documents/guides"),
  /* Served out of the image rather than the document register: a manual is
     not evidence, and the 2025 audit's register carries foundation documents
     only. */
  guideViewUrl: (name) =>
    `/api/documents/guides/${encodeURIComponent(name)}?inline=1`,
  guideDownloadUrl: (name) =>
    `/api/documents/guides/${encodeURIComponent(name)}`,

  documentViewUrl: (id) =>
    `/api/documents/${encodeURIComponent(id)}/file?inline=1`,
  documentDownloadUrl: (id) =>
    `/api/documents/${encodeURIComponent(id)}/file`,
  attachDocument: (body) =>
    req("/documents/attach", { method: "POST", body: JSON.stringify(body) }),
  /* What each unattached document looks like it supports. Applies nothing:
     a proposal is never a decision. */
  documentProposals: (period = "2025", limit = 60) =>
    req(`/documents/propose?period=${period}&limit=${limit}`),
  attachDocuments: (attachments) =>
    req("/documents/attach/bulk",
        { method: "POST", body: JSON.stringify({ attachments }) }),
  /* The amount, date and vendor on the face of a document. Transcription
     rather than judgment — but it decides what the matcher may propose, so
     it takes the portfolio that says what a document supports. */
  /* Asking for what only somebody else knows — three things nothing on the
     record can be made to infer. Issuing and replying are open to anybody
     who may read the period; accepting takes the portfolio that owns the
     data, because writing somebody's answer into the cost record is the same
     judgment as typing it in by hand. */
  requestForms: () => req("/requests/forms"),
  /* Where the nineteen things the record cannot settle on its own stand,
     and who said so. A read, so anybody who may read the record gets it —
     the auditor's first question about any of them is "who said that, and
     on what". */
  verificationStatus: (period = "2025") =>
    req(`/requests/verification?period=${period}`),
  requests: (period = "2025", state = "") =>
    req(`/requests?period=${period}${state ? `&state=${state}` : ""}`),
  issueRequest: (form, body) =>
    req(`/requests/${encodeURIComponent(form)}/issue`,
        { method: "POST", body: JSON.stringify(body) }),
  requestWorkbookUrl: (id) => `/api/requests/${id}/workbook`,
  requestPreview: (id) => req(`/requests/${id}/preview`),
  acceptRequest: (id, note = "") =>
    req(`/requests/${id}/accept`, { method: "POST", body: JSON.stringify({ note }) }),
  replyToRequest: (id, form) => sendForm(`/requests/${id}/reply`, form),
  documentFacts: (id, body) =>
    req(`/documents/${encodeURIComponent(id)}/facts`,
        { method: "PATCH", body: JSON.stringify(body) }),

  addReconcilingItem: (body) =>
    req("/reconcile/items", { method: "POST", body: JSON.stringify(body) }),
  retractReconcilingItem: (id, reason) =>
    req(`/reconcile/items/${id}/retract`, { method: "POST", body: JSON.stringify({ reason }) }),

  /* Working positions: the 757 the classification log proposed, what people
     have written against them, and what they have asked for instead. */
  positions: ({ period = "2025", state = "all", limit = 80, offset = 0,
                decision_id = "" } = {}) =>
    req(`/positions?period=${period}&state=${state}&limit=${limit}` +
        `&offset=${offset}` +
        (decision_id ? `&decision_id=${encodeURIComponent(decision_id)}` : "")),
  positionReview: (period = "2025") => req(`/positions/review?period=${period}`),
  confirmPositions: (decision_ids, note = "", period = "2025") =>
    req(`/positions/confirm?period=${period}`,
        { method: "POST", body: JSON.stringify({ decision_ids, note }) }),
  withdrawConfirmation: (decision_id, reason, period = "2025") =>
    req(`/positions/confirm/withdraw?period=${period}`,
        { method: "POST", body: JSON.stringify({ decision_id, reason }) }),
  /* Notes and recommendations reach four subjects: a classification group, a
     building, a space inside it, and one asset's funding. `decision_id` is
     the classification convenience the queue screens already send. */
  positionNotes: (decision_id, period = "2025") =>
    req(`/positions/notes?period=${period}&decision_id=${encodeURIComponent(decision_id)}`),
  subjectNotes: (subject, subject_id, period = "2025") =>
    req(`/positions/notes?period=${period}&subject=${subject}` +
        `&subject_id=${encodeURIComponent(subject_id)}`),
  recommend: (body, period = "2025") =>
    req(`/positions/recommend?period=${period}`,
        { method: "POST", body: JSON.stringify(body) }),
  /* 2 CFR 200.331, per party. The register has been on file since migration
     115 and had no door at all: six determinations worth $313,605.35 of MTDC,
     answerable only by writing SQL. */
  parties: (period = "2025") => req(`/classify/parties?period=${period}`),
  putDetermination: (body, period = "2025") =>
    req(`/classify/parties?period=${period}`,
        { method: "PUT", body: JSON.stringify(body) }),
  assetFunding: (period = "2025") =>
    req(`/facilities/asset-funding?period=${period}`),
  putAssetFunding: (body, period = "2025") =>
    req(`/facilities/asset-funding?period=${period}`,
        { method: "PUT", body: JSON.stringify(body) }),
  writeNote: (body, period = "2025") =>
    req(`/positions/notes?period=${period}`,
        { method: "POST", body: JSON.stringify(body) }),
  redesignateNote: (note_id, kind, reason, period = "2025") =>
    req(`/positions/notes/${note_id}?period=${period}`,
        { method: "PATCH", body: JSON.stringify({ kind, reason }) }),
  recommendReclass: (body, period = "2025") =>
    req(`/positions/recommend?period=${period}`,
        { method: "POST", body: JSON.stringify(body) }),
  acceptRecommendation: (id, body = {}, period = "2025") =>
    req(`/positions/recommendations/${id}/accept?period=${period}`,
        { method: "POST", body: JSON.stringify(body) }),
  declineRecommendation: (id, reason, period = "2025") =>
    req(`/positions/recommendations/${id}/decline?period=${period}`,
        { method: "POST", body: JSON.stringify({ reason }) }),
  withdrawRecommendation: (id, reason = "", period = "2025") =>
    req(`/positions/recommendations/${id}/withdraw?period=${period}`,
        { method: "POST", body: JSON.stringify({ reason }) }),
};

/* Money, to the cent, in one place.

   Eight screens carried their own spelling of this and six of them rounded to
   the whole dollar, so the record's $1,835,047.17 reached an auditor as
   $1,835,047 on the home screen and as $1,835,047.17 on the seal screen — one
   figure in two readings, which is the defect that produced 13.0% and 2.2% at
   the same moment in a smaller place. Everything behind the rendering is
   Decimal and exact; only the printing was lossy, and a cent is the unit a
   reviewer ties in.

   A blank is unanswered and prints as such. `Number(null || 0)` is 0, so the
   first version of this printed "nobody has read this off" and "this is nil"
   identically — the intake rule, applied to the screen.

   Negatives in parentheses, which is the accounting convention the workpapers
   already use and what a payables clerk reads. */
export const money = (n) => {
  if (n === null || n === undefined || n === "") return "\u2014";
  const v = Number(n);
  if (!Number.isFinite(v)) return "\u2014";
  return (v < 0 ? "(" : "") +
    Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2,
                                          maximumFractionDigits: 2 }) +
    (v < 0 ? ")" : "");
};

/* A count is not money. Groups, lines, documents and people are whole things
   and printing "757.00 groups" would be absurd; the separator is still wanted
   above a thousand. Kept beside money() so the choice is made by naming the
   thing rather than by reaching for the nearest formatter. */
export const count = (n) => {
  if (n === null || n === undefined || n === "") return "\u2014";
  const v = Number(n);
  if (!Number.isFinite(v)) return "\u2014";
  return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
};
