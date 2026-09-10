import React, { useState } from "react";
import { Card } from "../components/ui.jsx";

/* The manual, served by the application rather than sent round as a document,
   so it cannot drift from the thing it describes. Written for two readers who
   need very different amounts: Tom, who lives in it, and an employee who will
   open it once. */

const SECTIONS = [
  { id: "start", label: "Getting started" },
  { id: "dashboard", label: "The dashboard" },
  { id: "import", label: "Importing from QuickBooks" },
  { id: "classify", label: "Classifying cost" },
  { id: "segment", label: "Splitting a mixed line" },
  { id: "evidence", label: "Evidence and notes" },
  { id: "timesheet", label: "Your timesheet" },
  { id: "certify", label: "Certifying effort" },
  { id: "worklist", label: "What is left" },
  { id: "seal", label: "Sealing and rates" },
  { id: "export", label: "Giving the auditor the record" },
  { id: "roles", label: "Who can do what" },
  { id: "faq", label: "Questions" },
];

function Shot({ src, caption }) {
  return (
    <figure className="help-shot">
      <img src={src} alt={caption} loading="lazy" />
      <figcaption>{caption}</figcaption>
    </figure>
  );
}

function Q({ q, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`faq ${open ? "on" : ""}`}>
      <button className="faq-q" onClick={() => setOpen(!open)}>
        <span className="faq-mark">{open ? "−" : "+"}</span>{q}
      </button>
      {open && <div className="faq-a">{children}</div>}
    </div>
  );
}

export default function Help() {
  return (
    <div className="help">
      <nav className="help-nav">
        <div className="help-nav-title">Contents</div>
        {SECTIONS.map((s) => (
          <a key={s.id} href={`#${s.id}`}>{s.label}</a>
        ))}
      </nav>

      <div className="help-body">
        <h1>Using the cost allocation system</h1>
        <p className="lede">
          This system takes YBI's QuickBooks ledger, records what each cost is
          and why, attaches the evidence, and produces an indirect cost rate an
          auditor can follow back to source. Everything you do is recorded
          against you by name.
        </p>

        {/* ─────────────────────────────────────────────── */}
        <h2 id="start">Getting started</h2>
        <p>
          Go to the address IT gave you and sign in with your work email. There
          is no shared login: the whole point of the system is that every
          judgment has a person's name on it, so a shared account would make the
          record worthless.
        </p>
        <Shot src="/help/01-signin.png" caption="Sign in with your own account." />
        <p>
          Your account is created with a bootstrap password shared by everyone
          in the first setup. Change it the first time you sign in:{" "}
          <strong>Password</strong> in the top bar, beside your name. It asks
          for your current one, so nobody can change it from a screen you left
          open. Until you do, every signature the system holds in your name is
          one four other people could have written.
        </p>
        <p>
          If you forget it, ask Eric to reset it. There is no self-service
          reset by email yet.
        </p>

        {/* ─────────────────────────────────────────────── */}
        <h2 id="dashboard">The dashboard</h2>
        <p>
          Landing page for everyone except employees. Four blocks, top to
          bottom: where the finances stand, whether the controls tie, what is
          left to do, and what has happened recently.
        </p>
        <Shot src="/help/02-dashboard.png"
              caption="The dashboard. Income, expenses and net tie to the P&L you imported." />
        <p>
          <strong>Where the finances stand</strong> comes from the imported
          Profit and Loss, not from a separate calculation, so if it disagrees
          with QuickBooks the import is wrong and should be looked at before
          anything else.
        </p>
        <p>
          <strong>Dollar coverage</strong> is the number that matters. It is the
          share of cost in scope that has a live classification. It starts near
          zero and you are aiming at eighty per cent before sealing. Row counts
          are not a useful measure of progress — one line can be worth more than
          four hundred.
        </p>
        <p>
          <strong>Controls</strong> shows each derived figure and whether it
          reconciles to its source. A tick means it ties to the cent. A cross
          means it does not, and nothing downstream of it should be trusted
          until it does.
        </p>
        <p>
          <strong>Recent activity</strong> at the foot of the dashboard is read
          from the records themselves rather than from a separate log, so it
          cannot describe something that did not happen. Imports, classifications,
          splits, documents, notes, certifications, seals, sign-ins, downloads —
          each with the person who did it and when.
        </p>
        <Shot src="/help/04-activity.png"
              caption="The activity feed. Every entry names a person and a time." />

        {/* ─────────────────────────────────────────────── */}
        <h2 id="import">Importing from QuickBooks</h2>
        <p>
          Export from QuickBooks as CSV where it offers it — the Excel path
          merges cells and inserts formatting rows. Import the Profit and Loss
          first: it defines which accounts are cost and which are balance sheet,
          and without it the classification queue will ask you to classify bank
          accounts.
        </p>
        <Shot src="/help/05-import.png"
              caption="Drop each report in. Nothing reaches the ledger until it reconciles." />
        <p>
          Every import is a dry run until it ties.{" "}
          <strong>Nothing reaches the ledger until every subtotal QuickBooks
          printed in its own report matches what was parsed.</strong> If an
          import is refused, the message names the accounts that failed and by
          how much. That is usually a sign the export was filtered or a date
          range was wrong, not that the system is broken.
        </p>
        <p>
          Re-uploading the same file is safe. It is recognised by its content
          and will not create a second copy.
        </p>

        {/* ─────────────────────────────────────────────── */}
        <h2 id="classify">Classifying cost</h2>
        <p>
          The queue groups the ledger by account and payee and puts the largest
          groups first. For each group you record four independent things:
        </p>
        <ul>
          <li><strong>Pool</strong> — direct, fringe, overhead, G&amp;A,
            rental-direct, fundraising, unallowable or excluded.</li>
          <li><strong>Form 990 function</strong> — program, management and
            general, or fundraising.</li>
          <li><strong>Federal treatment</strong> — allowable, unallowable, not
            applicable or pending.</li>
          <li><strong>Evidence grade</strong> — how well supported the judgment
            is, from unsupported up to verified.</li>
        </ul>
        <Shot src="/help/06-classify-sweep.png"
              caption="Sweep mode: the dense table, for the many groups with an obvious answer." />
        <p>
          Press <code>f</code> for <strong>focus</strong> mode when a group needs
          real thought. One group at a time, the amount set large, the sample
          memos from the ledger for context, and the proposal as a single
          button. <code>j</code> and <code>k</code> move, <code>Enter</code>
          accepts, <code>1</code>–<code>8</code> jump to a pool,
          <code>/</code> searches.
        </p>
        <Shot src="/help/07-classify-focus.png"
              caption="Focus mode. The proposal is a suggestion; accepting it is your judgment." />
        <p>
          A proposal is never a decision. What the system infers from the
          account name, the Customer:Job field or last year is a suggestion you
          confirm. Where nothing points anywhere, it says so and the group stays
          in the queue rather than being defaulted into a pool.
        </p>
        <Shot src="/help/11-editor.png"
              caption="Classifying differently: pool, function, federal treatment, grade and the reasoning." />
        <p>
          Direct cost must name a cost objective; pooled cost must not. Anything
          graded above test assumption needs written reasoning. A verified grade
          needs a document cited on the judgment — attaching a file nearby is
          not the same thing, and the system will refuse the grade until the
          document is cited.
        </p>
        <p className="callout">
          <strong>No rate is shown while you classify, and that is deliberate.</strong>{" "}
          A reviewer will ask whether the rate was honest or worked backwards
          from a number you wanted. The answer has to be documentary. Seeing the
          rate move as you classify would destroy that, so the screens do not
          show it.
        </p>
        <p>
          If a group needs someone else's input, defer it with a reason rather
          than skipping it. Deferred is a state; skipped is an absence, and
          absences drift out of view.
        </p>

        {/* ─────────────────────────────────────────────── */}
        <h2 id="segment">Splitting a mixed line</h2>
        <p>
          A booked entry is often not one thing. Meals and entertainment mixes
          allowable business meals with unallowable entertainment; portfolio
          consulting is part direct and part general. Forcing such a group into
          one pool because the bookkeeping entry was aggregated is the mistake
          segmentation exists to prevent.
        </p>
        <p>
          Open the group in focus mode and choose <strong>Split this
          group</strong>. Each part takes a label, a share, the reasoning
          behind that share and its citation. The shares must come to a hundred
          per cent before the button will let you record anything.
        </p>
        <Shot src="/help/12-split.png"
              caption="Splitting $100,000 of portfolio consulting into a direct part and a general part." />
        <p>
          Every line reconciles to the cent — not the group in aggregate, each
          line — and a split into a single part is refused, because dividing
          something into one piece changes nothing while looking like a
          judgment. The source ledger is untouched: the parts sit beside it and
          become the unit you classify.
        </p>
        <Shot src="/help/13-split-recorded.png"
              caption="Recorded: two parts across eight lines, eight segments, reconciled." />
        <p>
          A segmentation can be reversed with a reason. The parts stay on the
          record marked reversed; they are never deleted.
        </p>

        {/* ─────────────────────────────────────────────── */}
        <h2 id="evidence">Evidence and notes</h2>
        <p>
          A <strong>note</strong> is for reasoning that belongs to the group
          rather than to a document — why the funding is state and not federal,
          a question for the CEO, a variance to come back to. Open{" "}
          <strong>Notes and documents</strong> on any group in focus mode.
          Mark it as a workpaper note if the auditor should see it, and they
          will.
        </p>
        <Shot src="/help/08-note.png"
              caption="A note being written against the group it explains." />
        <Shot src="/help/09-note-recorded.png"
              caption="Recorded against your name and the time. Notes are never edited in place." />
        <p>
          Attach the document that supports a judgment from the same panel, and
          say what it shows. One upload fans out to every line in the group, so
          the document supports the dollars rather than the screen.
        </p>
        <Shot src="/help/10-attached.png"
              caption="One upload, attached to all eight lines of the group." />
        <p>
          Documents are stored by their content, so the same lease attached to
          forty lines is stored once, and the file produced two years from now
          is provably the file relied on. The <strong>Evidence</strong> tab is
          the register: everything received, what it supports, and the file
          itself.
        </p>
        <Shot src="/help/14-evidence.png"
              caption="Schedule E. Anyone who can read the period can download the document." />

        {/* ─────────────────────────────────────────────── */}
        <h2 id="timesheet">Your timesheet</h2>
        <p>
          <strong>My time</strong> is your own record of your own time. Nobody
          else can enter time on it — not the controller, not an administrator
          — because a timesheet somebody else filled in is exactly what a
          certification is supposed to rule out.
        </p>
        <p>
          Two views. <strong>Week</strong> is for entering: objectives down the
          side, days across the top, type hours into the grid and tab along.
          <strong> Month</strong> is for finding your way around the year and
          seeing what is still blank; click any day to see what is on it.
        </p>
        <Shot src="/help/22-timesheet-week.png"
              caption="The week grid. One basis for the week, because that is how a person works back through a calendar." />
        <p>
          Before you enter a week, say <strong>what you are working from</strong>
          — your calendar, project records, a dated deliverable, or memory. It
          is recorded with the hours, because a reviewer is entitled to know
          what the number rests on.
        </p>
        <p className="callout">
          <strong>You cannot mark old time as contemporaneous.</strong> The
          system works out whether a record was made at the time by comparing
          the day worked with the day you typed it, and nothing else. Time
          entered within a week counts as contemporaneous. 2025 entered now is
          a reconstruction, however carefully you rebuild it — and a careful
          reconstruction is worth a great deal more than a bad one, so it is
          worth doing properly.
        </p>
        <Shot src="/help/23-timesheet-month.png"
              caption="The month view. Days with time carry the hours and a bar; blank days are the work left." />
        <h3>Paid leave</h3>
        <p>
          Record holidays, PTO and sick days against <strong>LEAVE</strong>.
          They are compensated time, so leaving them out would overstate every
          project share. Leave is recorded and then left out of the base, which
          is a different thing from ignoring it.
        </p>
        <h3>Submitting</h3>
        <p>
          Filling the sheet in is not the same as finishing it. While it is
          unsubmitted, the controller's reconstruction still speaks for your
          year; the moment you submit, your own record replaces it. That is why
          submission is a separate step, and why a part-filled sheet is refused:
          two days entered against one award would otherwise claim that award
          was your whole year.
        </p>
        <p>
          You say how many hours a week you worked, and the sheet has to cover
          at least ninety per cent of what that implies for the period. You can
          withdraw a submission with a reason; it stays on the record marked
          withdrawn.
        </p>
        <Shot src="/help/25-timesheet-summary.png"
              caption="What the sheet adds up to, and where it differs from the reconstruction built for you." />
        <p>
          The <strong>difference table</strong> is not a scolding. The 2025
          distribution was rebuilt from payroll and hours logs before anyone
          asked you, and where your own record disagrees with it, both stay on
          the file and the gap is shown in dollars. That difference is for the
          controller to look at — it is not something either side gets to
          overwrite.
        </p>

        {/* ─────────────────────────────────────────────── */}
        <h2 id="certify">Certifying effort</h2>
        <p>
          Employees sign for their own time. Nobody signs for anybody else — not
          Tom, not Eric. That is what 2 CFR 200.430(i) asks for: a statement by
          the person who did the work, or by a supervisor with firsthand
          knowledge of it.
        </p>
        <Shot src="/help/17-certify.png"
              caption="An employee sees their whole year, not just the federally funded part." />
        <p>
          The screen shows the <strong>whole</strong> distribution — every
          activity, federal or not. Certifying only the federally charged slice
          proves nothing about the denominator, which is what makes the
          percentages mean anything.
        </p>
        <Shot src="/help/18-certified.png"
              caption="Signed. The name, the time and the distribution as it stood are recorded together." />
        <p>
          If the distribution changes after you sign, your signature is marked{" "}
          <strong>stale</strong> rather than quietly carried over. It attested to
          different numbers. You will be asked to sign again, and both
          signatures stay on the record.
        </p>

        {/* ─────────────────────────────────────────────── */}
        <h2 id="worklist">What is left</h2>
        <p>
          The dashboard lists open work by class, ordered by money. Click any
          class to see the items.
        </p>
        <Shot src="/help/03-worklist.png"
              caption="Each class says why it is open and where it is resolved." />
        <p>
          <strong>Blocking</strong> items prevent a rate being sealed:
          unclassified cost, judgments graded unsupported or test assumption,
          effort nobody has certified, signatures gone stale, assets whose
          funding source is unknown, facilities with no space schedule.{" "}
          <strong>High</strong> and <strong>medium</strong> items are quality of
          the record rather than gates.
        </p>

        {/* ─────────────────────────────────────────────── */}
        <h2 id="seal">Sealing and rates</h2>
        <p>
          When coverage is high enough to defend, seal the decision set. Sealing
          hashes every live judgment and freezes them. Only then can a rate be
          computed, and the rate carries the seal.
        </p>
        <p>
          Changing a classification afterwards requires unsealing with a written
          reason, and unsealing supersedes the rate. This is not bureaucracy: it
          is the mechanism that lets you show the rate followed from the
          judgments rather than the judgments being fitted to a rate.
        </p>
        <p className="callout">
          Unclassified cost is never quietly assigned to a pool. While work is
          unfinished the rate reads high, which is the honest direction to err.
        </p>

        {/* ─────────────────────────────────────────────── */}
        <h2 id="export">Giving the auditor the record</h2>
        <p>
          The audit package downloads as one workbook: the controls and whether
          they tie, every judgment with its reasoning and citation, what was
          split and why, the evidence and what it supports, who signed for their
          effort and in what words, everything that happened, and what is still
          open.
        </p>
        <p>
          The auditor can have their own read-only account and download it
          themselves. A reviewer who has to ask you for a copy has the person
          being reviewed standing between them and the evidence.
        </p>
        <Shot src="/help/19-auditor.png"
              caption="The auditor's dashboard. The same figures, and their own copy of the record." />
        <p>
          Read-only is enforced at the server, and the screens reflect it: the
          auditor sees every group, every judgment, every note and document, and
          none of the controls that would change one.
        </p>
        <Shot src="/help/20-auditor-classify.png"
              caption="The queue as the auditor sees it — no checkboxes, no accept, no revise." />

        {/* ─────────────────────────────────────────────── */}
        <h2 id="roles">Who can do what</h2>
        <table className="help-table">
          <thead>
            <tr><th>Role</th><th>Can</th><th>Cannot</th></tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Controller</strong></td>
              <td>Import, classify, segment, attach evidence, note, seal,
                  restate, export, read anyone's timesheet</td>
              <td>Create accounts; enter time for anyone; certify anyone's
                  effort</td>
            </tr>
            <tr>
              <td><strong>Employee</strong></td>
              <td>Keep their own timesheet, submit it, and certify their own
                  effort</td>
              <td>See the ledger, classify, see or fill in anyone else's
                  timesheet, or certify for anyone else</td>
            </tr>
            <tr>
              <td><strong>Auditor</strong></td>
              <td>Read everything, download the package</td>
              <td>Change anything at all</td>
            </tr>
            <tr>
              <td><strong>Admin</strong></td>
              <td>Create and deactivate accounts</td>
              <td>Classify or seal — administering people and making cost
                  judgments are separate jobs</td>
            </tr>
          </tbody>
        </table>

        {/* ─────────────────────────────────────────────── */}
        <h2 id="faq">Questions</h2>

        <Q q="The system refused my import. What now?">
          The message names the accounts that did not tie and by how much.
          Almost always the export was filtered, or covered a different date
          range, or was taken before a period was closed. Re-export the whole
          period unfiltered. Nothing was written, so there is nothing to undo.
        </Q>

        <Q q="Why can I not see the rate while I am classifying?">
          Because a reviewer will ask whether the rate was honest or
          reverse-engineered, and the answer has to be something you can show
          rather than something you assert. Classifications are sealed first;
          the rate is computed from them afterwards and carries the seal. If the
          rate were visible during classification, nothing would stop it — or
          the appearance of it — steering the judgments.
        </Q>

        <Q q="I classified something wrongly. Can I change it?">
          Yes. Record the corrected judgment; it supersedes the old one, which
          stays on the record. Nothing is edited in place and nothing is
          deleted. If the decision set has already been sealed you will have to
          unseal it with a reason, and that supersedes the rate.
        </Q>

        <Q q="Can I sign an employee's certification for them if they are away?">
          No. An employee certification has to be theirs. A supervisor with
          firsthand knowledge of the work can certify on that basis instead, and
          it is recorded as a supervisor certification rather than passed off as
          the employee's.
        </Q>

        <Q q="Why is my signature marked stale?">
          Because the distribution changed after you signed it. The earlier
          signature attested to different numbers, so it no longer supports
          these. Review the new distribution and sign again — both signatures
          stay on the record, which is how anyone can see what was attested and
          when.
        </Q>

        <Q q="Dollar coverage is only 20%. Is the rate wrong?">
          The rate reads high while work is unfinished, because unclassified
          cost is never assumed into a pool. That is the honest direction to
          err — an incomplete rate that overstates is a rate you can defend and
          then reduce; one that understates has quietly assumed things nobody
          decided.
        </Q>

        <Q q="Someone changed a ledger line after I classified it.">
          It appears as a stale decision on the dashboard. The judgment may
          still be right, but it was made about different numbers, so re-decide
          it rather than letting it stand.
        </Q>

        <Q q="What does the auditor actually see?">
          Everything, read-only, and they can download the whole record
          themselves. Notes marked as workpaper notes are included. That is
          deliberate: a reviewer who can alter the record cannot attest to it,
          and one who cannot see all of it is not reviewing.
        </Q>

        <Q q="Can I delete something I uploaded by mistake?">
          Documents and judgments are not deletable. Detach a document, or
          supersede a judgment, and the record shows that it happened and why.
          A cost system where things can vanish cannot support an audit.
        </Q>

        <Q q="Do I have to rebuild all of 2025 to certify?">
          No. If you leave your timesheet unsubmitted, the controller's
          reconstruction stands and you certify that, which is what everyone
          did before timesheets existed. Submitting your own record is better
          evidence, and it is your call whether the year is worth rebuilding.
          From 2026 the same screen produces contemporaneous records simply by
          being used in the week the work happens, which is worth more than any
          reconstruction.
        </Q>

        <Q q="My hours disagree with the controller's figures. Which wins?">
          Yours, once you submit — the person who did the work is the
          firsthand record. Neither is deleted: the difference is shown in
          percentages and in dollars, and the controller looks at it. If the
          difference is large it usually means something real, like time spent
          on an award nobody thought to charge.
        </Q>

        <Q q="Who do I ask?">
          Tom Metzinger for anything about the numbers or the classifications.
          Eric Wagner for accounts and access.
        </Q>
      </div>
    </div>
  );
}
