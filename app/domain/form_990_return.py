"""The whole of Form 990 for one year, assembled from what the record says.

`form_990_field` is the register of every field outside the three financial
statements, and each row says *where its 2025 answer comes from*. This is what
reads that column — a small interpreter over the source expressions, and
nothing else.

**Four answers, and keeping them apart is the point.** A figure read from the
record, a line the form defines as another line of itself, a fact about the
organisation carried from the filed return, and a question nobody has answered.
The first two are measured and the last two are not, and a return that printed
them alike would get signed over a stale answer — which is the same rule
`v_rate_certified` holds for a rate and `invoice_document.py` holds for a
reproduction.

Pure: no database, no rendering. The caller reads the rows and hands them in,
so the assembly can be tested without Postgres and so no second copy of a
figure is made on the way through.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from decimal import Decimal

#: The Part IX line the form takes *out* of the statement of functional
#: expenses and nets against Part VIII line 8a instead. It is a line of the
#: register like any other and must never be counted in a Part IX total.
NETTED = "8b"

#: What each answer means on the face of the return. Written down once, because
#: three screens keeping their own copy of a vocabulary is the defect this
#: repository has paid for most often.
PROVENANCE = {
    "record":  "read from the record",
    "field":   "another line of this return",
    "carried": "carried from the 2024 return — confirm",
    "ask":     "not answered for this year",
}


class Unresolved(Exception):
    """A source expression the interpreter does not understand.

    Loud rather than silent: a source that quietly resolved to zero would put
    a figure on a tax return with nothing behind it, which is the one outcome
    this whole module exists to prevent.
    """


@dataclass(frozen=True)
class Field:
    field_id: str
    part: str
    seq: int
    line_no: str
    label: str
    kind: str
    answer: str
    source: str
    note: str
    prior: str = ""


@dataclass
class Answer:
    """One field, answered. `value` is None where nobody has answered it —
    which is not the same fact as zero, and the renderer prints them apart."""
    field: Field
    value: object | None
    provenance: str
    says: str = ""

    @property
    def answered(self) -> bool:
        return self.value is not None and self.value != ""


@dataclass
class Context:
    """Everything already read from the record, by the caller."""
    period: str
    ix: dict = dc_field(default_factory=dict)       # line_id -> {col: Decimal}
    viii: dict = dc_field(default_factory=dict)     # line_id -> Decimal
    x: dict = dc_field(default_factory=dict)        # line_id -> Decimal
    fn: dict = dc_field(default_factory=dict)       # name -> value
    fields: dict = dc_field(default_factory=dict)   # field_id -> Field


def _d(x) -> Decimal:
    return Decimal(str(x or 0))


def _split(payload: str) -> list[str]:
    """Top-level comma split.

    `add:` arguments may not themselves contain a comma, so an `ixsum` or a
    nested `add` inside one is refused rather than mis-parsed. The limitation
    is worth having loudly: silently taking the first fragment would produce a
    plausible figure, and a plausible wrong figure on a tax return is the
    worst shape available.
    """
    parts = payload.split(",")
    for p in parts:
        if p.startswith(("add:", "ixsum:")):
            raise Unresolved(f"a comma-bearing source nested in a list: {p}")
    return parts


def resolve(source: str, ctx: Context, seen: frozenset = frozenset()):
    """Answer one source expression. Returns a Decimal, a value, or None."""
    if not source:
        raise Unresolved("an empty source")

    head, _, rest = source.partition(":")

    if head == "ix":
        line, _, col = rest.partition(":")
        return _d(ctx.ix.get(line, {}).get(col or "total"))

    if head == "ixsum":
        lines, _, col = rest.rpartition(":")
        return sum((_d(ctx.ix.get(ln.strip(), {}).get(col or "total"))
                    for ln in lines.split(",")), Decimal(0))

    if head == "ixtotal":
        # Every line of Part IX except the one the form nets in Part VIII.
        col = rest or "total"
        return sum((_d(v.get(col)) for k, v in ctx.ix.items() if k != NETTED),
                   Decimal(0))

    if head == "viii":
        return _d(ctx.viii.get(rest))

    if head == "x":
        return _d(ctx.x.get(rest))

    if head in ("x16", "x26", "x32"):
        return _d(ctx.fn.get(head))

    if head == "neg":
        return -_d(resolve(rest, ctx, seen))

    if head == "add":
        return sum((_d(resolve(p, ctx, seen)) for p in _split(rest)),
                   Decimal(0))

    if head == "sub":
        a, _, b = rest.partition(",")       # exactly two, first comma splits
        return _d(resolve(a, ctx, seen)) - _d(resolve(b, ctx, seen))

    if head == "field":
        if rest in seen:
            raise Unresolved(f"a field that refers back to itself: {rest}")
        f = ctx.fields.get(rest)
        if f is None:
            raise Unresolved(f"a reference to a field that is not on the "
                             f"register: {rest}")
        return answer(f, ctx, seen | {rest}).value

    if head == "fn":
        if rest not in ctx.fn:
            raise Unresolved(f"a computed field the caller did not read: {rest}")
        return ctx.fn[rest]

    raise Unresolved(f"a source expression nobody reads: {source}")


def answer(f: Field, ctx: Context, seen: frozenset = frozenset()) -> Answer:
    """One field, answered, with how it was answered on it."""
    if f.answer in ("record", "field"):
        return Answer(f, resolve(f.source, ctx, seen), PROVENANCE[f.answer])

    if f.answer == "carried":
        # The filed return's own answer stands, and says that it does. An
        # empty prior is an empty answer rather than a missing one: the 2024
        # return left the field blank and so does this one.
        return Answer(f, f.prior, PROVENANCE["carried"])

    # ask: the value is None, which is not zero and not blank. What is wanted
    # is on the field and travels with it.
    return Answer(f, None, PROVENANCE["ask"], f.source)


def assemble(fields: list[Field], ctx: Context) -> list[Answer]:
    """Every field of the return, in the order the form prints them."""
    ctx.fields = {f.field_id: f for f in fields}
    return [answer(f, ctx) for f in sorted(fields, key=lambda f: f.seq)]


def outstanding(answers: list[Answer]) -> list[Answer]:
    """What the return could not answer. This is the list that has to reach
    the first page — a reviewer handed a total has formed a view before they
    reach a footnote."""
    return [a for a in answers if a.field.answer == "ask"]


def carried(answers: list[Answer]) -> list[Answer]:
    """What stands on last year's answer. Not a defect and not a measurement:
    it is the list somebody confirms before signing."""
    return [a for a in answers if a.field.answer == "carried"]
