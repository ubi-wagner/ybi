import React, { useEffect, useState } from "react";
import { api, explain } from "../api.js";
import { Card, Drawer, Empty, PageHead, Pill } from "../components/ui.jsx";

/* The guidebook.
 *
 * The manuals and the generated PDFs, on a shelf, for anybody signed in.
 * They existed as files in `docs/` and as rows in the library, which meant
 * the controller could find them by searching a register of cost evidence
 * and an employee could not reach them at all — the everybody manual is
 * written for exactly that person, and reading the cost record is a grant
 * they do not have.
 *
 * Three rules, and the second is the one that shapes the page.
 *
 * Nothing here is computed. The title, the note, whose job it describes and
 * whether it can be shown in the page all come from the answer. A screen
 * that decided for itself which manual is yours would be a second copy of a
 * rule the server already holds, free to drift from it.
 *
 * **Yours is an ordering and never a filter.** The manual inside the
 * application is assembled from what the reader holds so that it never
 * describes a screen they cannot open; a shelf is the other case. An
 * employee who cannot see that a controller's manual exists learns the
 * shelf is short, which is the same defect as a nav stricter than the API
 * wearing different clothes.
 *
 * And a guide opens in the page. Somebody reading the run sheet beside the
 * screen it describes should not have to leave for a downloads folder — the
 * same reason the library opens a lease inline, under the same two locks on
 * the response.
 */

function size(bytes) {
  const n = Number(bytes || 0);
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/* What a guide is, said in the words the person already uses for themselves.
   The server sends the audience; this only spells it. */
const AUDIENCE = {
  everybody: "Everybody",
  CONTROLLER: "The controller",
  admin: "The administrator",
  AUDITOR: "The auditor",
};

function GuideCard({ guide, onOpen }) {
  const openable = guide.inline_safe;
  return (
    <Card variant={guide.yours ? "raised" : "quiet"} className="guide-card">
      <div className="guide-head">
        <h3 className="guide-title">{guide.title}</h3>
        {guide.yours
          ? <Pill tone="accent">Yours</Pill>
          : <Pill>{AUDIENCE[guide.audience] || guide.audience}</Pill>}
      </div>
      <p className="guide-note">{guide.note}</p>
      <div className="guide-foot">
        <span className="rowsub">
          {guide.name}{size(guide.byte_size) ? ` · ${size(guide.byte_size)}` : ""}
        </span>
        <span className="guide-actions">
          {openable && (
            <button className="btn" onClick={() => onOpen(guide)}>Read</button>
          )}
          {/* A download is one click away whichever it is, because a manual
              somebody wants beside them on a train is a real need — and for
              anything the browser will not render in the page it is the only
              honest offer rather than a button that does nothing. */}
          <a className="btn quiet"
             href={api.guideDownloadUrl(guide.name)}
             download={guide.name}>
            {openable ? "Download" : "Download to read"}
          </a>
        </span>
      </div>
    </Card>
  );
}

export default function Guidebook() {
  const [state, setState] = useState({ loading: true });
  const [open, setOpen] = useState(null);

  useEffect(() => {
    api.guides()
      .then((d) => setState({ ...d, loading: false }))
      .catch((e) => setState({ loading: false, failed: e }));
  }, []);

  if (state.loading) return null;

  const guides = state.guides || [];
  const yours = guides.filter((g) => g.yours);
  const rest = guides.filter((g) => !g.yours);

  return (
    <div className="guidebook">
      <PageHead title="Guidebook" schedule="?"
        aside={<span className="rowsub">
          {state.total} on the shelf · {state.yours} for your job
        </span>} />

      {/* "Not yet, because", never an empty page. A shelf with nothing on it
          is nearly always a deployment that has not filed them rather than a
          system with no manuals, and saying which is the difference between
          a question for the administrator and a shrug. */}
      {state.failed && (
        <Empty mark="!" title="The guidebook could not be read">
          {explain(state.failed)}
        </Empty>
      )}
      {!state.failed && !guides.length && (
        <Empty mark="—" title="Nothing has been filed yet">
          The manuals are filed when the application starts. If this stays
          empty, the deployment is missing <code>docs/</code> — ask whoever
          runs it.
        </Empty>
      )}

      {Boolean(yours.length) && (
        <>
          <h2 className="section-head">For your job</h2>
          <div className="guide-grid">
            {yours.map((g) => (
              <GuideCard key={g.name} guide={g} onOpen={setOpen} />
            ))}
          </div>
        </>
      )}

      {Boolean(rest.length) && (
        <>
          <h2 className="section-head">Everything else on the shelf</h2>
          <p className="lede quiet-note">
            Written for somebody else's job, and readable. Knowing what the
            auditor is working from is worth as much as your own chapter.
          </p>
          <div className="guide-grid">
            {rest.map((g) => (
              <GuideCard key={g.name} guide={g} onOpen={setOpen} />
            ))}
          </div>
        </>
      )}

      <Drawer open={Boolean(open)} wide
              title={open?.title || ""}
              subtitle={open?.name || ""}
              onClose={() => setOpen(null)}
              footer={open && (
                <a className="btn" href={api.guideDownloadUrl(open.name)}
                   download={open.name}>Download</a>
              )}>
        {open && (
          /* No `sandbox` attribute, and it must not grow one. Chromium
             refuses to run its PDF viewer inside a sandboxed frame at every
             value of the attribute, and three of these eight are PDFs. The
             sandbox that matters is the one the server puts in the
             response's Content-Security-Policy, which Chromium honours and
             still renders a PDF under — and which travels with the file
             when it is opened outside this panel. */
          <iframe className="doc-frame" title={open.title}
                  src={api.guideViewUrl(open.name)} />
        )}
      </Drawer>
    </div>
  );
}
