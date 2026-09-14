import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/* Shared primitives. Deliberately small: the pages should read as content,
   not as a wiring diagram. */

/* One page heading, used by every screen.

   There were two: `.page-head` with an h2 and a lede on ten pages, and
   `.dash-head` with an h1 and a `.quiet` line on four. Same job, two heading
   levels, two type sizes and two colours — which reads as carelessness on a
   screen somebody opens every morning, and gives a screen reader a document
   outline that changes shape depending on which tab is open.

   `schedule` is the letter the tab prints as in the audit package. Somebody
   who has seen the workpapers knows where they are from it, so it belongs
   next to the title rather than buried in the sentence underneath. */
export function PageHead({ title, schedule, children, aside }) {
  return (
    <div className="page-head">
      <div className="page-head-row">
        <h1>
          {title}
          {schedule && <span className="page-sched">{schedule}</span>}
        </h1>
        {aside && <div className="page-head-aside">{aside}</div>}
      </div>
      {children && <p className="lede">{children}</p>}
    </div>
  );
}

export function Card({ title, aside, children, variant = "", className = "", ...rest }) {
  return (
    <section className={`card ${variant} ${className}`} {...rest}>
      {(title || aside) && (
        <div className="card-head">
          {title && <div className="card-title">{title}</div>}
          {aside && <div className="rowsub">{aside}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, note, size = "md", tone }) {
  return (
    <div>
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${size}`} style={tone ? { color: `var(--${tone})` } : undefined}>
        {value}
      </div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  );
}

export function Pill({ tone = "", children }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

/* Tick marks, the way a reviewer would annotate a schedule. */
const TICKS = {
  done:    { glyph: "✓", title: "Classified" },
  open:    { glyph: "", title: "Not yet reviewed" },
  flagged: { glyph: "△", title: "Needs attention" },
  failed:  { glyph: "✕", title: "Fails a constraint" },
};

export function Tick({ state = "open", title }) {
  const t = TICKS[state] || TICKS.open;
  return <span className={`tick ${state}`} title={title || t.title} aria-label={title || t.title}>{t.glyph}</span>;
}

export function Meter({ pct, target = 80, good = false }) {
  const clamped = Math.max(0, Math.min(100, Number(pct) || 0));
  return (
    <div>
      <div className={`meter ${good ? "good" : ""}`}>
        <i style={{ width: `${clamped}%` }} />
      </div>
      <div className="meter-marks">
        <span style={{ left: `${target}%` }}>{target}% target</span>
      </div>
    </div>
  );
}

export function Field({ label, hint, required, children }) {
  return (
    <label className="field">
      <div className="field-label">
        <span>{label}</span>
        {required && <span className="req">required</span>}
        {hint && !required && <span>{hint}</span>}
      </div>
      {children}
    </label>
  );
}

export function Segmented({ options, value, onChange }) {
  return (
    <div className="seg" role="tablist">
      {options.map(([v, label]) => (
        <button key={v} role="tab" aria-selected={value === v}
                className={value === v ? "on" : ""} onClick={() => onChange(v)}>
          {label}
        </button>
      ))}
    </div>
  );
}

export function Search({ value, onChange, placeholder = "Search" }) {
  return (
    <div className="search">
      <span className="glyph" aria-hidden>⌕</span>
      <input value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

export function Table({ columns, children, footer }) {
  /* A column is {label, align, width}. A bare string is accepted too, and
     read as a left-aligned label: passing one used to render an empty header
     cell, which is a silent failure — the table looked deliberate and told
     the reader nothing. */
  const cols = columns.map((c) =>
    typeof c === "string" ? { label: c, align: "left" } : c);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {cols.map((c, i) => (
              <th key={i} className={c.align === "left" ? "l" : ""} style={c.width ? { width: c.width } : undefined}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
        {footer && <tfoot>{footer}</tfoot>}
      </table>
    </div>
  );
}

export function Empty({ mark = "—", title, children, action }) {
  return (
    <div className="empty">
      <div className="mark" aria-hidden>{mark}</div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}

export function Keys({ hints }) {
  return (
    <div className="keyhints">
      {hints.map(([k, what]) => (
        <span key={k}>
          {k.split("/").map((key) => <kbd key={key}>{key}</kbd>)} {what}
        </span>
      ))}
    </div>
  );
}

/* `wide` is for a drawer that carries tables rather than a form — a contract
   with its terms, milestones, invoices and the money against each does not
   read in a 560px column. */
export function Drawer({ open, title, subtitle, onClose, footer, wide = false,
                         children }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className={`drawer ${wide ? "wide" : ""}`} role="dialog"
             aria-modal="true" aria-label={title}>
        <header>
          <div>
            <h3 style={{ fontSize: 17 }}>{title}</h3>
            {subtitle && <div className="rowsub">{subtitle}</div>}
          </div>
          <button className="ghost" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="body">{children}</div>
        {footer && <footer>{footer}</footer>}
      </aside>
    </>
  );
}

/* Toasts double as the undo surface. Nothing here is destructive without a
   way back — the fastest way to make someone slow and cautious is to make
   mistakes expensive. */

const ToastCtx = createContext(() => {});

/* What a screen gets from `useToast()`.
 *
 * Callable, and also carrying `.show`, `.fail`, `.ok` and `.warn` — because
 * half this application called `toast(...)` and the other half called
 * `toast.show(...)`, the context value was a bare function, and seventeen
 * call sites across five screens threw `TypeError: toast.show is not a
 * function` instead of saying anything.
 *
 * Most of those seventeen were inside `catch` blocks. So a write would fail,
 * the error handler would fail, and the person would be told nothing at all —
 * which is worse than an ugly error and is the exact thing a notification
 * exists to prevent. Barb could create an account, have it refused, and see
 * an unchanged screen.
 *
 * Supporting both spellings is not indecision. One of them was always going
 * to be written by somebody, and a surface that throws on a plausible call is
 * a surface that will be called that way again. */
function toaster(push) {
  const fn = (message, opts) => push(message, opts);
  fn.show = fn;
  fn.ok = (message, opts = {}) => push(message, { ...opts, tone: "ok" });
  fn.warn = (message, opts = {}) => push(message, { ...opts, tone: "warn" });
  fn.fail = (message, opts = {}) => push(message, { ...opts, tone: "fail" });
  return fn;
}

export const useToast = () => useContext(ToastCtx);

/* Tone names that have been used in this codebase, mapped to the three that
 * mean something. "bad" and "fail" were both in use and only "bad" was
 * rendered, so nine error toasts came out looking exactly like a success
 * message — a failure notification indistinguishable from a confirmation.
 *
 * Anything unrecognised is treated as a failure rather than as plain. Getting
 * a red toast for a tone somebody misspelled is a small cost; showing an
 * error as a confirmation is not. */
const TONES = {
  ok: "ok", good: "ok", success: "ok",
  warn: "warn", warning: "warn",
  bad: "fail", fail: "fail", error: "fail", danger: "fail",
};

function toneOf(raw) {
  if (!raw) return "";
  const t = TONES[String(raw).toLowerCase()];
  if (t) return t;
  if (import.meta.env?.DEV) {
    console.error(
      `[toast] unknown tone "${raw}" — rendering as a failure. Known tones: `
      + Object.keys(TONES).join(", "));
  }
  return "fail";
}

export function ToastHost({ children }) {
  const [items, setItems] = useState([]);

  const push = useCallback((message, opts = {}) => {
    const id = Math.random().toString(36).slice(2);
    const tone = toneOf(opts.tone);
    /* A failure stays until it is dismissed. One that disappears after six
       seconds while somebody is looking at a different part of the screen is
       the same as no notification, and this system's whole claim is that you
       can tell what happened. Confirmations still fade; nobody needs to
       acknowledge that a thing worked. */
    const sticky = opts.sticky ?? tone === "fail";
    setItems((x) => [...x, { ...opts, id, message, tone, sticky }]);
    if (!sticky) {
      setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)),
                 opts.ms || 6000);
    }
    return id;
  }, []);

  const dismiss = (id) => setItems((x) => x.filter((i) => i.id !== id));
  const value = useMemo(() => toaster(push), [push]);
  const failing = items.some((t) => t.tone === "fail");

  return (
    <ToastCtx.Provider value={value}>
      {children}
      {/* assertive while something has failed, so a screen reader announces
          it rather than waiting for a pause. */}
      <div className="toasts" role={failing ? "alert" : "status"}
           aria-live={failing ? "assertive" : "polite"}>
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.tone}`}>
            <span style={{ flex: 1 }}>
              {t.tone === "fail" && <strong>Failed — </strong>}
              {t.message}
            </span>
            {t.onUndo && (
              <button className="sm" onClick={() => { t.onUndo(); dismiss(t.id); }}>Undo</button>
            )}
            <button className="sm ghost" style={{ color: "#fff" }}
                    onClick={() => dismiss(t.id)} aria-label="Dismiss">✕</button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
