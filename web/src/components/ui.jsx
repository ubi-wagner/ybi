import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

/* Shared primitives. Deliberately small: the pages should read as content,
   not as a wiring diagram. */

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
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((c, i) => (
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

export function Drawer({ open, title, subtitle, onClose, footer, children }) {
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
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title}>
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
export const useToast = () => useContext(ToastCtx);

export function ToastHost({ children }) {
  const [items, setItems] = useState([]);

  const push = useCallback((message, opts = {}) => {
    const id = Math.random().toString(36).slice(2);
    setItems((x) => [...x, { id, message, ...opts }]);
    if (!opts.sticky) setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), opts.ms || 6000);
    return id;
  }, []);

  const dismiss = (id) => setItems((x) => x.filter((i) => i.id !== id));

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.tone === "bad" ? "bad" : ""}`}>
            <span style={{ flex: 1 }}>{t.message}</span>
            {t.onUndo && (
              <button className="sm" onClick={() => { t.onUndo(); dismiss(t.id); }}>Undo</button>
            )}
            <button className="sm ghost" style={{ color: "#fff" }} onClick={() => dismiss(t.id)}>✕</button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
