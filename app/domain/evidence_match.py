"""Proposing which cost a document supports.

Twenty-one documents on file and **none attached to a single ledger line**,
so no judgment in the record can be graded `VERIFIED` — the deferred trigger
`decision_verified_check` refuses the whole set otherwise — and the ceiling
on every one of the controller's two hundred decisions is `CORROBORATED`.
Attaching them one at a time through `/api/documents/attach` is two hundred
round trips of reading an invoice and hunting a group.

So this proposes. It does not decide: **a proposal is never a decision**, the
rule `propose()` already follows in the classification queue, and the rule
that makes the whole system worth auditing. What comes out of here is a
suggestion with its reasons written out, and a person presses the key.

## The signal has to exist before it can be scored

`evidence.doc_amount`, `doc_date` and `vendor_name` are columns four views
read and **nothing had ever written** — the same shape as `rate.superseded_by`
and `space_partition`, both of which turned out to be defects rather than
spare capacity. Every one of the forty-three documents on file carried NULL
in all three. A matcher over that has nothing to match on, so the upload and
the document facts route fill them first, and a document that says nothing
about itself proposes nothing and says so.

## Amount is necessary, and nothing else is sufficient

A document proposes only where its amount equals a candidate's, to the cent.
Date proximity and vendor similarity **raise confidence and break ties**;
neither can carry a proposal alone. An invoice dated in March near a group
that ran in March is not evidence that it is *that* group's invoice, and a
matcher willing to say so would put the controller's name on an attachment
nobody checked.

## More than one candidate means no candidate

The rule `/api/reconcile/propose` follows, and the asset schedule's variance
attribution, and for the same reason: **an attribution that could equally
have been something else is not evidence**. Where two candidates tie at the
top score, nothing is proposed and the reason names how many tied, so the
person knows to look rather than assuming there was nothing to find.

Pure, no database — the engine can be run over a list and tested without
Postgres, like every other module in `domain/`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.domain.core import money

#: How far from the cost a document may be dated and still be about it.
#:
#: A month either side of the period the group covers. An invoice is raised
#: before the cost is booked and paid after it; three weeks is ordinary and
#: six is not unusual across a month end. Wider than this stops being a
#: signal — at ninety days it matches most of a quarter and contributes
#: nothing but the appearance of confidence.
DATE_WINDOW_DAYS = 31

#: Words that say what kind of company something is, not which one.
#:
#: "Acme Inc" and "Acme LLC" are the same signal about the same vendor, and
#: leaving these in makes every limited company slightly similar to every
#: other. They are dropped from both sides before comparison.
LEGAL_FORMS = frozenset({
    "inc", "incorporated", "llc", "llp", "lp", "ltd", "limited", "co",
    "corp", "corporation", "company", "plc", "pllc", "pc", "gmbh", "sa",
    "nv", "bv", "ag", "the", "and", "of",
})

_WORD = re.compile(r"[a-z0-9]+")


def tokens(name: str) -> frozenset[str]:
    """The words in a name that say *which* party it is.

    Lowercased, punctuation dropped, legal forms removed. "Youngstown
    Business Incubator, Inc." and "YOUNGSTOWN BUSINESS INCUBATOR" come out
    the same, which is the point — the ledger's payee and a letterhead are
    written by different people on different days.
    """
    return frozenset(w for w in _WORD.findall(name.lower())
                     if w not in LEGAL_FORMS and len(w) > 1)


def similarity(a: str, b: str) -> float:
    """How much two party names have in common, 0 to 1.

    Jaccard over the significant words. Deliberately simple and explicable:
    the proposal has to say *why* in a sentence somebody can check, and
    "three of four words match" is checkable in a way that a distance from
    an embedding is not. An empty name on either side is 0 — no signal, not
    a perfect match to nothing.
    """
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


#: Below this, two names are different parties. A single shared word out of
#: four or five is coincidence — "Ohio" appears in a great many of them.
VENDOR_FLOOR = 0.34


@dataclass(frozen=True)
class Document:
    """What a document says about itself."""
    evidence_id: str
    filename: str = ""
    doc_amount: Decimal | None = None
    doc_date: date | None = None
    vendor_name: str = ""

    @property
    def says_nothing(self) -> bool:
        return self.doc_amount is None


@dataclass(frozen=True)
class Target:
    """A cost a document might be about — a ledger group or one line."""
    target_type: str          # LEDGER_GROUP or LEDGER_LINE
    target_id: str
    label: str
    amount: Decimal
    payee: str = ""
    first_day: date | None = None
    last_day: date | None = None
    lines: int = 1


@dataclass(frozen=True)
class Signal:
    """One reason, in the words it will be shown in."""
    name: str
    says: str
    weight: int


@dataclass(frozen=True)
class Match:
    target: Target
    signals: tuple[Signal, ...]

    @property
    def score(self) -> int:
        return sum(s.weight for s in self.signals)

    @property
    def because(self) -> str:
        return " ".join(s.says for s in self.signals)


@dataclass(frozen=True)
class Proposal:
    """One document, and the single candidate that fits — or none, and why."""
    document: Document
    match: Match | None = None
    considered: int = 0
    runners_up: tuple[Match, ...] = field(default_factory=tuple)
    why_not: str = ""

    @property
    def proposes(self) -> bool:
        return self.match is not None


def _amount_signal(doc: Document, t: Target) -> Signal | None:
    if doc.doc_amount is None:
        return None
    if money(doc.doc_amount) != money(t.amount):
        return None
    where = (f"across {t.lines} lines" if t.lines > 1 else "on the line")
    return Signal("AMOUNT", f"The amount matches to the cent, {where}.", 100)


def _date_signal(doc: Document, t: Target) -> Signal | None:
    if doc.doc_date is None or t.first_day is None or t.last_day is None:
        return None
    if t.first_day <= doc.doc_date <= t.last_day:
        return Signal("DATE", "Dated inside the period the cost was booked in.", 20)
    gap = min(abs((doc.doc_date - t.first_day).days),
              abs((doc.doc_date - t.last_day).days))
    if gap <= DATE_WINDOW_DAYS:
        return Signal("DATE", f"Dated {gap} day{'s' if gap != 1 else ''} from "
                              f"the cost.", 10)
    return None


def _vendor_signal(doc: Document, t: Target) -> Signal | None:
    if not doc.vendor_name or not t.payee:
        return None
    score = similarity(doc.vendor_name, t.payee)
    if score < VENDOR_FLOOR:
        return None
    shared = sorted(tokens(doc.vendor_name) & tokens(t.payee))
    return Signal("VENDOR",
                  f"The vendor reads as the same party as {t.payee!r} "
                  f"({', '.join(shared)}).",
                  30 if score >= 0.8 else 15)


def weigh(doc: Document, target: Target) -> Match | None:
    """One document against one candidate. None where the amount does not."""
    amount = _amount_signal(doc, target)
    if amount is None:
        return None
    signals = [amount]
    for maybe in (_date_signal(doc, target), _vendor_signal(doc, target)):
        if maybe is not None:
            signals.append(maybe)
    return Match(target=target, signals=tuple(signals))


def propose(doc: Document, targets: list[Target]) -> Proposal:
    """The one candidate that fits, or none and the reason.

    Ties at the top score propose nothing. Not the first of them, not the
    largest, not the most recent — nothing, because any of those would be a
    rule invented to avoid saying "I do not know", and the person reading
    the attachment later would have no way to tell it apart from a match
    somebody checked.
    """
    if doc.says_nothing:
        return Proposal(
            document=doc, considered=len(targets),
            why_not=("This document does not say what it is for. Record its "
                     "amount — and its date and vendor where they are on the "
                     "face of it — and it can be matched. Nothing is guessed "
                     "from a filename."))

    matches = [m for m in (weigh(doc, t) for t in targets) if m is not None]
    if not matches:
        return Proposal(
            document=doc, considered=len(targets),
            why_not=(f"No cost in the period comes to "
                     f"{money(doc.doc_amount)}. Either it is not a ledger "
                     f"amount — a total across periods, a figure before tax "
                     f"— or it supports something other than one group."))

    best = max(m.score for m in matches)
    top = [m for m in matches if m.score == best]
    if len(top) > 1:
        return Proposal(
            document=doc, considered=len(targets),
            runners_up=tuple(sorted(top, key=lambda m: m.target.label)),
            why_not=(f"{len(top)} different costs fit this document equally "
                     f"well. Any one of them would be a guess, so none is "
                     f"proposed — open it and say which."))
    return Proposal(document=doc, match=top[0], considered=len(targets),
                    runners_up=tuple(sorted((m for m in matches if m is not top[0]),
                                            key=lambda m: -m.score))[:3])


def propose_all(docs: list[Document], targets: list[Target]) -> list[Proposal]:
    """Every document against the same candidates.

    A document already proposed for one cost is not withheld from another:
    one invoice can genuinely support two groups, and refusing the second
    would be the matcher making a judgment rather than offering one.
    """
    return [propose(d, targets) for d in docs]
