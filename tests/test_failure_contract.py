"""What happens when something does not work.

The complaint these answer is precise: Tom presses a button, the system
declines, and nothing tells him. Three ways that happened, all of them found
by reading the code rather than by anything failing:

  * `useToast()` returned a bare function and seventeen call sites across
    five screens called `toast.show(...)`, which throws. Most were inside
    `catch` blocks, so a failed write made the error handler fail and the
    person was told nothing at all.
  * `ToastHost` rendered only `tone === "bad"`, and nine sites passed
    `tone: "fail"` — so those errors came out in the ordinary treatment,
    visually identical to a confirmation.
  * Thirty-two screens load with `.catch(() => {})`, so a failed read renders
    an empty table and "nothing yet" is indistinguishable from "the request
    failed".
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "web" / "src" / "components" / "ui.jsx"
API = ROOT / "web" / "src" / "api.js"
SRC = ROOT / "web" / "src"
SQL = ROOT / "app" / "sql"


def test_the_toast_surface_supports_every_way_it_is_called():
    """Both spellings, because both were written.

    A surface that throws on a plausible call is one that will be called that
    way again. Supporting both is not indecision.
    """
    ui = UI.read_text()
    assert "fn.show = fn" in ui, (
        "useToast() no longer answers toast.show(...). Seventeen call sites "
        "use it, most inside catch blocks — they would throw instead of "
        "reporting the failure they were written to report.")

    used = set()
    for f in SRC.rglob("*.jsx"):
        src = f.read_text()
        if "useToast()" not in src:
            continue
        used |= set(re.findall(r"\btoast\.(\w+)\(", src))
    for call in used:
        assert f"fn.{call} =" in ui or call == "show", (
            f"a screen calls toast.{call}(), which the toast surface does "
            f"not provide")


def test_every_tone_in_use_renders_as_something():
    """"bad" and "fail" were both written and only "bad" had a rule."""
    ui = UI.read_text()
    css = (ROOT / "web" / "src" / "theme.css").read_text()

    tones = set()
    for f in SRC.rglob("*.jsx"):
        tones |= set(re.findall(r'tone:\s*"(\w+)"', f.read_text()))
    # Pill and Stat take tones too; only the toast ones need a .toast rule.
    known = set(re.findall(r"^\s*(\w+):\s*\"(?:ok|warn|fail)\",", ui, re.M))
    known |= set(re.findall(r"(\w+):\s*\"(?:ok|warn|fail)\"", ui))
    for tone in tones:
        assert tone in known or f".{tone}" in css, (
            f'tone "{tone}" is used and is neither mapped by the toast '
            f"surface nor styled. An error shown in the ordinary treatment "
            f"is a failure that looks like a confirmation.")

    for tone in ("fail", "ok", "warn"):
        assert f".toast.{tone}" in css, f".toast.{tone} has no rule"


def test_a_failure_does_not_disappear_on_its_own():
    """A notification that fades in six seconds while somebody is looking
    somewhere else is the same as no notification."""
    ui = UI.read_text()
    assert 'opts.sticky ?? tone === "fail"' in ui, (
        "failures no longer stay until dismissed")


def test_an_unrecognised_tone_is_treated_as_a_failure():
    """Getting a red toast for a misspelled tone is a small cost. Showing an
    error as a confirmation is not."""
    ui = UI.read_text()
    m = re.search(r"function toneOf\(raw\) \{(.*?)\n\}", ui, re.S)
    assert m, "toneOf is gone"
    assert 'return "fail";' in m.group(1), (
        "an unknown tone no longer falls back to the failure treatment")


def test_no_request_failure_can_be_swallowed_by_a_call_site():
    """Thirty-two screens catch a failed read and do nothing with it.

    Fixing thirty-two call sites works until the thirty-third is written, so
    the record is taken underneath them all, in `req` itself, where a caller
    cannot forget it.
    """
    api = API.read_text()
    assert "function noteFailure(" in api, (
        "the request layer no longer records failures, so a screen that "
        "catches and ignores one leaves no trace anywhere in the client")
    m = re.search(r"async function req\(path, opts = \{\}\) \{(.*?)\n\}",
                  api, re.S)
    assert m, "req is gone"
    body = m.group(1)
    assert body.count("noteFailure(") >= 3, (
        "not every failure path in req records: a transport error, a 403 and "
        "any other bad status are three different failures")
    # 401 deliberately does not record — it is a state to move to, and
    # recording it would fill the list every time a session expires.
    assert "if (res.status === 401) throw new Unauthorized" in body


def test_the_shell_surfaces_what_the_screens_swallowed():
    app = (SRC / "App.jsx").read_text()
    assert "FailureBell" in app, (
        "nothing in the shell shows the failures the request layer recorded")
    bell = (SRC / "components" / "FailureBell.jsx").read_text()
    # **The rule, not the line.** This asserted the literal
    # `if (!items.length) return null;` and failed the day the panel grew a
    # second source — the server's own `refusal` register — while still
    # obeying the rule perfectly. Same defect as
    # `test_the_crosswalk_refuses_to_guess_a_split` asserting the punctuation
    # of the source it was written about: a test that argues against working
    # code is worse than no test.
    guard = re.search(r"if \(([^)]*)\)\s*return null;", bell)
    assert guard, (
        "the failure indicator must return null when it has nothing to say. "
        "A permanent status light that is green all day is one nobody looks "
        "at on the day it turns red.")
    sources = re.findall(r"!(\w+)\.length", guard.group(1))
    assert sources, "the guard must be on emptiness, not on a flag"
    for name in sources:
        assert re.search(rf"const \[{name}, set", bell), (
            f"the guard reads {name}, which is not state this component holds")
    # Every list it renders has to be in the guard, or the bell can hide a
    # record it is holding.
    rendered = set(re.findall(r"\{(\w+)\.map\(", bell))
    assert rendered <= set(sources), (
        "these are rendered in the panel and not in the emptiness guard, so "
        "the bell can hide something it is holding: "
        + ", ".join(sorted(rendered - set(sources))))


def test_a_refused_write_is_on_the_record():
    """`audit_log` records changes, so by construction it records nothing
    when a change does not happen — which leaves the most frustrating case
    documented nowhere."""
    joined = "\n".join(p.read_text() for p in sorted(SQL.glob("*.sql")))
    assert "CREATE TABLE refusal" in joined
    assert "refusal_is_a_refusal" in joined, (
        "nothing stops a success being written to the refusal table")

    mw = (ROOT / "app" / "refusals.py").read_text()
    assert "class RecordRefusals" in mw
    assert "MUTATING" in mw, (
        "refusals are recorded for reads too; a refused GET is usually "
        "somebody opening a screen they do not hold, and it would bury the "
        "writes that matter")
    # Recording a refusal must never turn a refusal into a crash.
    assert "except Exception" in mw and "log.exception" in mw, (
        "a failure to record a failure would become a 500 on a request that "
        "had already been answered")


def test_the_middleware_can_name_the_person():
    """A refusal recorded as anonymous when the caller was signed in and
    merely lacked a portfolio says something was refused and not to whom."""
    auth = (ROOT / "app" / "auth.py").read_text()
    assert "request.state.actor = actor" in auth, (
        "current_actor no longer stashes the actor, so middleware that never "
        "reaches a handler cannot name anybody")


def test_a_reclassification_supersedes_rather_than_stacking():
    """A second judgment on a decided group used to answer 200 and do
    nothing.

    `one_live_decision_per_unit` stops a line carrying two live decisions, and
    the line insert swallowed the conflict with ON CONFLICT DO NOTHING. So a
    reclassification produced a live decision with *no lines*: the handler
    said "decisions_created: 1", the pools still read the old pool, two live
    decisions disagreed with each other, and the controller was told it had
    worked.

    That is the worst shape a defect can take here — not a refusal, which is
    visible, but a success that does nothing, over the figures a rate is
    built from.
    """
    src = (ROOT / "app" / "routers" / "classify.py").read_text()
    m = re.search(r"def decide\(.*?\n(?=\n@router)", src, re.S)
    assert m, "the decide handler is gone"
    body = m.group(0)

    assert "reversed_at = now()" in body, (
        "decide() no longer reverses the judgment it replaces, so a "
        "reclassification will attach to no lines and silently do nothing")
    assert "superseded" in body, "decide() no longer tracks what it replaced"
    assert "attached != len(with_lines)" in body, (
        "decide() no longer checks that its lines landed. ON CONFLICT DO "
        "NOTHING is how the silent success was possible; the handler has to "
        "verify rather than assume.")


def test_coverage_counts_a_line_once_however_often_it_was_judged():
    """Reclassifying leaves the superseded `decision_line` in place with
    `live = false`. A view joining on `line_id` alone then counts the line
    twice — one reclassification took `classified` from 2,219,105.55 to
    exactly double, and the *scope* grew, which is the tell: no judgment
    anybody makes can change how much there is to judge.
    """
    joined = "\n".join(p.read_text() for p in sorted(SQL.glob("*.sql")))
    m = re.findall(
        r"CREATE OR REPLACE VIEW v_classification_coverage AS(.*?);\s*COMMENT",
        joined, re.S)
    assert m, "v_classification_coverage is gone"
    body = m[-1]                       # the latest definition wins
    assert "dl.live" in body, (
        "coverage joins decision_line without filtering dl.live, so every "
        "reclassified line is counted once per judgment it has ever carried")


def test_the_propagation_matrix_asserts_both_directions():
    """A figure that moves when it should not is as much a defect as one
    that does not move when it should, and only the second kind ever gets
    noticed."""
    drive = (ROOT / "scripts" / "drive_propagation.py").read_text()
    assert "MUST_HOLD" in drive and "MAY_MOVE" in drive, (
        "the propagation drive no longer says what must hold, so it can only "
        "catch half the defects")
    assert "nothing said it could" in drive, (
        "the drive no longer reports a figure that moved without being "
        "listed — which is how the coverage double-count was found")


def test_an_undo_that_walked_nothing_back_is_not_a_success():
    """It answered 200 with `undone: []` and the reasons buried in the body.

    Every caller checks the status, and a state machine drive counted forty
    successes over one actual undo. The information was there the whole time
    and nothing said to read it.
    """
    src = (ROOT / "app" / "routers" / "undo.py").read_text()
    m = re.search(r"def undo\(body: UndoIn.*?\n(?=\n@router|\Z)", src, re.S)
    assert m, "the undo handler is gone"
    body = m.group(0)
    assert "if not done:" in body and "409" in body, (
        "an undo that walks nothing back no longer refuses; it will report "
        "success over having done nothing")


def test_a_settled_entry_does_not_jam_the_undo_trail():
    """Undo walks newest first, which is right — undoing out of order puts a
    value back that a later action moved on from. But there was no way *past*
    an entry that can never be undone, and one sits in the ordinary
    lifecycle: seal, compute, unseal, and the SEAL entry is offered for ever
    while answering "that set is not sealed".

    Everything older than it — every classification, every document — became
    permanently unreachable. A drive walked back forty times and moved one
    thing.
    """
    joined = "\n".join(p.read_text() for p in sorted(SQL.glob("*.sql")))
    m = re.findall(r"CREATE OR REPLACE VIEW v_undoable AS(.*?);\s*COMMENT",
                   joined, re.S)
    assert m, "v_undoable is no longer redefined"
    body = m[-1]
    assert "already_undone" in body
    assert "WHEN 'SEAL' THEN NOT EXISTS" in body, (
        "a seal whose set has since been unsealed is still offered as "
        "undoable, and blocks everything older than it")
    assert "WHEN 'CLASSIFY' THEN EXISTS" in body, (
        "a classification a later judgment superseded is still offered as "
        "undoable")


def test_the_state_machine_refuses_to_start_from_an_unknown_state():
    """Every expectation in it is an absolute count from a known start, so a
    second run over the first run's leavings measures from the wrong zero —
    which is exactly what it did, reporting two findings that were really its
    own arithmetic."""
    drive = (ROOT / "scripts" / "drive_state_machine.py").read_text()
    assert "COULD NOT RUN — the record is not at rest" in drive
    assert "decisions_live" in drive and "rates_all" in drive


def test_the_state_machine_checks_every_invariant_every_turn():
    """A chain reaction that goes wrong two turns downstream is invisible to
    a check that only looks at what it expected to change."""
    drive = (ROOT / "scripts" / "drive_state_machine.py").read_text()
    assert "INVARIANTS = [" in drive
    n = drive.count('     """SELECT count(*)')
    assert n >= 10, f"only {n} invariants; the set has been thinned out"
    m = re.search(r"def turn\(.*?\n(?=\ndef )", drive, re.S)
    assert m and "check_invariants(" in m.group(0), (
        "turn() no longer re-checks the invariants, so it can only catch a "
        "defect in the thing it was already looking at")


def test_the_reset_is_bounded_to_the_drive_s_own_actions():
    """An undo loop that ran to exhaustion would carry on into the seed and
    start reversing the eighteen foundational documents. That is not a reset,
    it is demolition."""
    drive = (ROOT / "scripts" / "drive_state_machine.py").read_text()
    assert "floor" in drive and "entry_id > %s" in drive, (
        "the reset is no longer bounded by an audit floor")


def test_no_screen_reaches_past_the_request_layer():
    """`req` records, and for six calls nothing did.

    The test above proves the request layer takes the record underneath every
    call site. It never proved the call sites *go through it* — and six did
    not. `Imports.jsx` ran the whole import cycle on bare `fetch(...).then(x
    => x.json())`, and `Awards.jsx` opened its drawer the same way.

    Both failed in the way this file exists for. A refused import comes back
    as `{detail: "..."}` with a 4xx, which parses perfectly: `lines_promoted`
    is undefined, `?? 0` fills in, and the screen says "0 lines added to the
    ledger" in the tone it uses for success — a refusal over the general
    ledger, reported as nothing having happened. A 403 on the award drawer
    parsed the same way and was then handed to `.map`, which took the page
    down; a network error rejected a promise nobody awaited, so the row
    simply did not open and no trace of it reached anything.

    So the rule is the one `tests/test_storage_paths.py` already holds for
    the volume: there is one door, and a screen that grows its own is the
    defect rather than a shortcut.
    """
    offenders = []
    for path in sorted(SRC.rglob("*.jsx")):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"(?<![.\w])fetch\s*\(", line.split("//")[0]) \
               and not line.lstrip().startswith(("*", "/*")):
                offenders.append(f"{path.relative_to(SRC)}:{n}: {line.strip()}")
    assert not offenders, (
        "a screen calls fetch() directly, so its failures never reach "
        "noteFailure() and an error body is read as a result:\n  "
        + "\n  ".join(offenders)
        + "\nAdd a helper to web/src/api.js instead.")


def test_a_multipart_upload_records_its_failures_too():
    """The three upload helpers cannot use `req` — setting Content-Type by
    hand drops the boundary the browser generates and the server sees no file
    — so they were hand-rolled, and each checked `res.ok` and stopped there.
    A failed upload threw a sentence a screen might catch and left nothing on
    the failure list at all, which is precisely what `FailureBell` exists to
    surface. One helper now, recording the same three ways `req` does.
    """
    api = API.read_text()
    m = re.search(r"async function sendForm\(path, form, opts = \{\}\) \{(.*?)\n\}",
                  api, re.S)
    assert m, ("the multipart helper is gone; the upload routes are back to "
               "hand-rolled fetches that record nothing")
    body = m.group(1)
    assert body.count("noteFailure(") >= 3, (
        "sendForm does not record every failure path: a transport error, a "
        "403 and any other bad status are three different failures")
    assert "if (res.status === 401) throw new Unauthorized" in body


#: Every place a write can land on nothing and still answer 200, and the
#: field that says so. Each one is reachable — a batch already promoted, a
#: group key the queue has moved past, a reply where every row came back
#: unusable — and each read as a confirmation before this.
LANDED_ON_NOTHING = [
    ("pages/Imports.jsx", "lines_promoted", "the general ledger"),
    ("pages/Requests.jsx", "r.written", "a reply nobody can send twice"),
    ("pages/ClassifyQueue.jsx", "attached_to", "a document filed against no cost"),
]


def test_a_write_that_landed_on_nothing_does_not_read_as_success():
    """An honest number in a sentence that reads as success.

    This is the shape the file above records shipping once already: *"the
    handler said `decisions_created: 1`, the pools still read the old pool,
    two live decisions disagreed with each other, and the controller was told
    it had worked."* The count was right and the tone was wrong, which is
    worse than a wrong count — nobody re-reads a green toast.

    So where a write can succeed and reach nothing, the screen says so in the
    failure-adjacent tone and says it stickily. A warning that fades in six
    seconds while somebody is looking at the preview is the same as no
    warning.
    """
    for rel, field, why in LANDED_ON_NOTHING:
        src = (SRC / rel).read_text()
        assert field in src, f"{rel} no longer reads {field}"
        assert "toast.warn(" in src and "sticky: true" in src, (
            f"{rel} can write nothing and say nothing about it — {why}. "
            "A zero here has to reach the person in a tone that is not the "
            "one used for success, and it has to stay on screen.")
