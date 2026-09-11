import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

/* The manual, on the landing page, assembled from what the person holds.
 *
 * Not a separate Help site nobody visits. A first-time user is looking at
 * their own landing page with no idea what to do next, and that is the only
 * moment the instructions are wanted — so they are here, one click from
 * closed, and they cover exactly the screens this person actually has.
 *
 * Every screenshot is a real screen, taken by scripts/walk_manuals.py while
 * signed in as somebody with that job, against the real ledger. A manual
 * illustrated with a mock-up goes stale the first time a button moves; this
 * one goes stale only if nobody re-runs the walk, which the drive does.
 *
 * Whether a chapter appears follows the same rule as the nav: `needs` is null
 * for everyone, "staff" for anybody on the payroll, "admin" for a
 * provisioner, otherwise a portfolio. Never describe a screen the reader
 * cannot open. */

const CHAPTERS = [
  {
    id: "start",
    needs: null,
    title: "Signing in, and your first five minutes",
    lede: "What happens the first time, and why it asks what it asks.",
    steps: [
      ["Choose your own password.",
       "The one you were handed is known to two people. Everything you record " +
       "here carries your name, so until the password is yours alone the " +
       "system will not let you record anything at all. It is one step and " +
       "it never comes back."],
      ["You land on your own page.",
       "Not everybody's. What you see is built from what you have been given " +
       "to do — if a tab is not there, it is not yours, and nothing on your " +
       "page will refuse you when you click it."],
      ["Anything you change is on the record.",
       "Every entry, every classification, every document names you and the " +
       "moment you did it. That is the point of the system rather than a " +
       "side effect of it, and it is what makes your signature worth having."],
    ],
    shot: ["role-06-first-password", "The first screen, and the only one " +
                                     "until it is done."],
  },
  {
    id: "time",
    needs: "staff",
    title: "Your timesheet",
    lede: "Rebuilding 2025 from whatever you actually have.",
    steps: [
      ["Work from your records, not your memory.",
       "A calendar, a project log, an email trail, a shop log. Say which one " +
       "you used — the system asks because a reconstruction that names its " +
       "source is evidence and one that does not is a guess."],
      ["A week at a time is faster than a day at a time.",
       "Most weeks look like the week before. Fill one, then move on; " +
       "nothing has to be right on the first pass."],
      ["Over eight hours a day, or forty a week, is questioned — not refused.",
       "Long days happen. The system asks you to say why, once, and then " +
       "accepts it. What it will not do is let a long day pass without a " +
       "word, because that is the one an auditor asks about."],
      ["Submit when the year looks right.",
       "Submitting is what makes your timesheet count towards your effort " +
       "rather than the reconstruction somebody else did for you."],
    ],
    shot: ["m-timesheet", "The calendar. Click a day, pick what you were " +
                          "working on, say where the hours came from."],
  },
  {
    id: "certify",
    needs: "staff",
    title: "Certifying your effort",
    lede: "The signature only you can give.",
    steps: [
      ["Read the distribution first.",
       "It shows how your year's pay is spread across the things you worked " +
       "on. If it looks wrong, fix the timesheet — do not sign it and hope."],
      ["Only you can sign it.",
       "2 CFR 200.430(i) wants a statement from the person who did the work. " +
       "A certification signed on your behalf is not that, and the system " +
       "refuses to let anybody try."],
      ["The words you sign are kept.",
       "Not a tick box — the actual statement, stored with your name and the " +
       "date, so a reviewer can read what you attested to."],
    ],
    shot: ["m-certify", "Your distribution, the statement, and the signature."],
  },
  {
    id: "documents",
    needs: null,
    title: "Sending documents in",
    lede: "Anything that shows what a cost was for.",
    steps: [
      ["Send it in even if you do not know where it belongs.",
       "A receipt, an invoice, a project plan, a photograph of a machine's " +
       "nameplate, a lease you were quoted. Say what it relates to in your " +
       "own words; somebody with the right portfolio decides what it proves."],
      ["You will see what became of it.",
       "Every document you send shows as waiting or in use. Nothing " +
       "disappears into a drawer, which is where all of this was before."],
      ["The same document twice is one document.",
       "It is recognised by its contents, so there is no harm in sending " +
       "something you are not sure about."],
    ],
    shot: ["m-documents", "Drop a file, say what it relates to, send it."],
  },
  {
    id: "classify",
    needs: "CONTROLLER",
    title: "Classifying cost",
    lede: "The screen the engagement turns on.",
    steps: [
      ["The queue is ordered by money.",
       "Largest first, because that is the order it is worth doing in. Press " +
       "f for focus mode on anything that needs real thought."],
      ["Four independent judgments per group.",
       "Cost pool, Form 990 function, federal treatment, and how well " +
       "supported it is. The last one is not optional politeness — it is " +
       "what the materiality policy reads."],
      ["Advice is never a decision.",
       "The system will tell you what an account name suggests and what the " +
       "same account was treated as elsewhere, each with the rule it rests " +
       "on. You decide; it records that you did."],
      ["Nothing is defaulted into a pool.",
       "Anything without a signal stays in the queue. That makes the rate " +
       "read high while work is unfinished, which is the honest direction " +
       "to be wrong in."],
      ["j and k move, Enter accepts, 1–8 jump to a pool, / searches.",
       "There are around two hundred meaningful decisions. Every second saved " +
       "compounds."],
    ],
    shot: ["m-classify", "Sweep mode: the dense table, for groups with an " +
                         "obvious answer."],
  },
  {
    id: "reconcile",
    needs: "CONTROLLER",
    title: "Making the books agree",
    lede: "Schedule A-1, before anything else.",
    steps: [
      ["Run it before you classify.",
       "Ten checks across the ledger, the profit and loss and the balance " +
       "sheet. A reconciliation produced after the rate is one nobody has a " +
       "reason to believe."],
      ["A difference is closed by naming it, not by netting it.",
       "Where accounts disagree, ask the system to find the lines behind the " +
       "difference. Where exactly one set of lines adds up, it shows them; " +
       "where more than one would, it proposes nothing, because a guess is " +
       "not evidence."],
      ["No rate while a check is open.",
       "A rate over a ledger that does not match its own statements is a " +
       "rate over the wrong numbers, however carefully the pools were built."],
    ],
    shot: ["m-reconcile", "Ten cross-reference points, and what is left at " +
                          "each."],
  },
  {
    id: "seal",
    needs: "CONTROLLER",
    title: "Sealing, and the rate",
    lede: "The order is the whole guarantee.",
    steps: [
      ["Classify first. No rate is shown while you do.",
       "A reviewer will ask whether the rate was honest or worked backwards " +
       "from. The answer has to be documentary, and this is the document."],
      ["Seal the decision set.",
       "Every live judgment is hashed together. After that, changing a " +
       "classification means unsealing with a reason — which supersedes any " +
       "rate that rested on it."],
      ["Only then can a rate be computed.",
       "It carries the seal. A database trigger refuses a rate whose seal " +
       "does not match a sealed set, so this holds even if the application " +
       "is wrong."],
      ["Both proofs run before anything is written.",
       "The pools reconcile to the ledger, and every allocable dollar lands " +
       "on exactly one objective — or you get a finding instead of a rate."],
    ],
    shot: ["m-rates", "Seal, then rate. Never the other way round."],
  },
  {
    id: "import",
    needs: "CONTROLLER",
    title: "Importing from QuickBooks",
    lede: "Nothing reaches the ledger until it ties.",
    steps: [
      ["Profit and loss first.",
       "It defines which accounts are cost and which are balance sheet. " +
       "Without it the queue will ask you to classify bank accounts."],
      ["Every import is a dry run until it reconciles.",
       "Every subtotal QuickBooks printed in its own report has to match what " +
       "was parsed. If it is refused, the message names the accounts and the " +
       "amounts — usually a filtered export or a wrong date range."],
      ["Re-uploading the same file is safe.",
       "It is recognised by its contents and will not create a second copy."],
    ],
    shot: ["m-imports", "Drop each report in. It ties, or it does not land."],
  },
  {
    id: "space",
    needs: "FACILITIES",
    title: "Buildings and space",
    lede: "What each space would fetch, beside what it was charged.",
    steps: [
      ["Record the building, then the suites inside it.",
       "Usable area, rentable area, and who is in each one."],
      ["A market rate has to say where it came from.",
       "A comparable, a survey, an appraisal. A rate with no basis is a " +
       "number somebody made up, and the system refuses it."],
      ["Below-market space on YBI's own building is not cost share.",
       "2 CFR 200.465 allows a less-than-arm's-length rental only up to what " +
       "ownership actually cost, so forgone rent on your own building is not " +
       "a cost you incurred. Record it as mission value — it is worth having, " +
       "it just does not go on a federal report."],
    ],
    shot: ["m-space", "The rent roll, with the subsidy each space carries."],
  },
  {
    id: "inventory",
    needs: "INVENTORY",
    title: "Equipment and inventory",
    lede: "The register, and what its use was worth.",
    steps: [
      ["Record what each machine is and where it stands.",
       "Programme equipment eating common lab floor is a real allocation " +
       "driver, not a detail."],
      ["Log who used it and what they were charged.",
       "Hours say who a machine served; square footage only says where it " +
       "stands. Free use by an incubator client is recorded at nil, not " +
       "left out."],
      ["An hourly rate needs a basis too.",
       "Same rule as space. What would it have cost them elsewhere, and how " +
       "do you know."],
    ],
    shot: ["m-inventory", "The register, subsidy by machine, and the lab " +
                          "floor it consumes."],
  },
  {
    id: "contracts",
    needs: "PROJECT",
    title: "Contracts and charge codes",
    lede: "What each contract earns, and who may charge it.",
    steps: [
      ["Every contract carries its ceiling, its cost share and its terms.",
       "A ceiling is not a contract — what may be charged and when it is " +
       "paid live in clauses, so each provision is recorded with the clause " +
       "it came from."],
      ["A milestone is what an invoice claims against.",
       "Without one, a payment arrives with nothing to say what it was for."],
      ["Money in is recorded against the invoice that earned it.",
       "Invoiced less received is the number worth chasing; received more " +
       "than invoiced is worth finding before the sponsor does."],
      ["A charge code is a cost objective — the same one the ledger is " +
       "classified into.",
       "So an hour and a dollar spent on the same work land in the same " +
       "place. There is no second list."],
      ["Assign people to a code before they charge it.",
       "Charging is gated on codes that have somebody assigned. A code with " +
       "an empty list predates the mechanism and stays open, which is what " +
       "makes reconstructing 2025 possible."],
      ["Nobody assigns themselves.",
       "The same rule the portfolios follow, for the same reason."],
    ],
    shot: ["m-contracts", "Contracts, what each has earned, and what it has " +
                          "cost so far."],
  },
  {
    id: "charge-codes",
    needs: "PROJECT",
    title: "Opening a charge code",
    lede: "Before anybody books an hour to it.",
    steps: [
      ["Open the code, say what it is, and say why.",
       "The reason goes on the record — a code with no purpose is a code " +
       "somebody will charge anything to."],
      ["A federal code needs its CFDA number.",
       "Without it the award cannot reach the SEFA, and the Single Audit " +
       "scope is decided by what is on the SEFA."],
      ["Assign the people who will work on it, with their role.",
       "An assignment can carry a window: an engagement that ends in June " +
       "should not be chargeable in July."],
      ["Taking somebody off keeps the grant, revoked.",
       "It does not delete it. Who could charge what, and when, is part of " +
       "the record."],
    ],
    shot: ["m-charge-codes", "Every code, who is assigned, and what has been " +
                             "charged to it."],
  },
  {
    id: "library",
    needs: "reader",
    title: "The document library",
    lede: "Reading the papers behind the numbers.",
    steps: [
      ["Everything anybody has sent in is here.",
       "Filed or not. The inbox is a queue of work; this is the whole shelf, " +
       "and it is where you go when you want to read a particular document " +
       "rather than deal with a backlog."],
      ["Open one to read it, or take a copy.",
       "A PDF, a photograph or a plain file opens in the page, which is what " +
       "you want when you are checking eleven attachments against eleven " +
       "figures. Download the one that is going into a workpaper."],
      ["A spreadsheet says so rather than doing nothing.",
       "Anything the page cannot show is marked no preview and downloads. " +
       "That is not a fault — it opens in the application it belongs to."],
      ["Search the way you remember it.",
       "The name, the vendor, who sent it, what they said it related to, or " +
       "the EV- identifier from a workpaper."],
      ["Every open and every copy is recorded against your name.",
       "Which is what makes it safe for this screen to show the whole shelf " +
       "rather than only what you filed yourself."],
    ],
    shot: ["m-library", "Everything on file, with what it is and who sent it."],
  },
  {
    id: "evidence",
    needs: "OFFICE",
    title: "Filing what people send in",
    lede: "Turning what people sent in into evidence.",
    steps: [
      ["The inbox is what nobody has filed yet.",
       "Somebody sent it in and said what it relates to. Deciding what it " +
       "supports is your judgment, not theirs."],
      ["Say why it is relevant.",
       "A document filed near a number is not evidence for it. The system " +
       "asks for the words, and they go in the file."],
      ["Coverage is measured in dollars, not documents.",
       "The question is what share of the cost is supported, which is the " +
       "one an auditor asks."],
    ],
    shot: ["m-evidence", "What is waiting, and what each document supports."],
  },
  {
    id: "people",
    needs: "admin",
    title: "Setting people up",
    lede: "Accounts, access, and who let whom in.",
    steps: [
      ["You create accounts below you, never beside you.",
       "Nobody provisions a peer or a superior — the database refuses it as " +
       "well as the screen does."],
      ["Set a password and hand it over.",
       "They will be made to choose their own before they can record " +
       "anything, so a password you know never signs anything."],
      ["A portfolio is authority over part of the cost record.",
       "Grant only what somebody needs, with a reason — the reason goes in " +
       "the file. Nobody, including you, grants themselves one."],
      ["Accounts are never deleted, only stood down.",
       "Every judgment, certification and upload points at an account. " +
       "Removing one would orphan the record it authorised."],
      ["Check the derived addresses.",
       "The payroll register gave surnames only, so the seeded email " +
       "addresses are a guess from the naming pattern. Anybody whose address " +
       "is wrong cannot sign in, and their account is sitting in the right " +
       "one's place."],
    ],
    shot: ["m-people", "The roster: rank, what they may judge, what they may " +
                       "read, and who let them in."],
  },
];

function visible(actor, needs) {
  if (!needs) return true;
  if (needs === "staff") return Boolean(actor.employee_key);
  if (needs === "admin") return Boolean(actor.is_admin);
  // The same rule the nav follows. Without it "reader" falls through to the
  // portfolio test and is false for everybody but the auditor — so the
  // organisation's administrator would be given the Library tab and no
  // chapter explaining it, which is the mismatch this function exists to
  // prevent, running the other way.
  if (needs === "reader") return Boolean(actor.can_read);
  if (actor.role === "AUDITOR") return true;
  return (actor.portfolios || []).includes(needs);
}

export default function Manual({ actor }) {
  const chapters = CHAPTERS.filter((ch) => visible(actor, ch.needs));
  const [open, setOpen] = useState(null);
  const [seen, setSeen] = useState(true);

  // First visit opens the manual. After that it stays out of the way — a
  // panel that reopens every morning becomes something people click past
  // without reading, which is worse than not having it.
  useEffect(() => {
    let stored = null;
    try { stored = window.localStorage.getItem("ybi:manual-seen"); } catch { /* private window */ }
    if (!stored) {
      setSeen(false);
      setOpen(chapters[0]?.id ?? null);
      try { window.localStorage.setItem("ybi:manual-seen", "1"); } catch { /* fine */ }
    }
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  if (!chapters.length) return null;

  return (
    <div className="card manual">
      <div className="manual-head">
        <div>
          <h3>How this works</h3>
          <p className="rowsub">
            {seen
              ? `${chapters.length} short chapters, covering the screens you have.`
              : "A few minutes, and it covers everything you can do here."}
          </p>
        </div>
        <Link className="btn quiet" to="/help">Full help</Link>
      </div>

      <div className="manual-chapters">
        {chapters.map((ch) => {
          const isOpen = open === ch.id;
          return (
            <div key={ch.id} className={`manual-chapter${isOpen ? " on" : ""}`}>
              <button className="manual-toggle"
                      aria-expanded={isOpen}
                      onClick={() => setOpen(isOpen ? null : ch.id)}>
                <span className="manual-mark" aria-hidden>{isOpen ? "−" : "+"}</span>
                <span>
                  <strong>{ch.title}</strong>
                  <span className="rowsub"> — {ch.lede}</span>
                </span>
              </button>
              {isOpen && (
                <div className="manual-body">
                  <ol>
                    {ch.steps.map(([what, why]) => (
                      <li key={what}>
                        <strong>{what}</strong>
                        <div className="rowsub">{why}</div>
                      </li>
                    ))}
                  </ol>
                  {ch.shot && (
                    <figure className="manual-shot">
                      <img src={`/help/${ch.shot[0]}.png`} alt={ch.shot[1]}
                           loading="lazy" />
                      <figcaption>{ch.shot[1]}</figcaption>
                    </figure>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
