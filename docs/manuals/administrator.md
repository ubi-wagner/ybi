# For the administrator

You hand out access. You do not judge cost, and you hold no portfolio — those
are different jobs and keeping them apart is the point.

## Two axes, not one

**Rank** is the provisioning ladder and runs only downward. A system
administrator sets up the organisation's administrator; you set up controllers
and employees; nobody provisions a peer or a superior. A database trigger
enforces the same rule, so it holds even when a screen is wrong.

Rank says who creates accounts and **nothing else**. `SYSTEM_ADMIN` is
deliberately not a reader of the cost record: standing the software up is not
a reason to read every employee's timesheet.

**Portfolio** is authority over part of the cost record, held as a set:
`CONTROLLER`, `INVENTORY`, `PROJECT`, `FACILITIES`, `OFFICE`. `CONTROLLER` is
the main one and reaches everything. The narrow ones reach only their own area
and **never add up to `CONTROLLER`** — only `CONTROLLER` may seal, unseal,
compute a rate or restate.

**Nobody grants themselves a portfolio.** The table refuses it and so does the
screen, including for you.

## Creating an account

**You create below you, never beside you.** The screen will not offer it and
the database would refuse it anyway.

**Set a password and hand it over.** They will be made to choose their own
before they can record anything, so a password you know never signs anything.
That is the rule that makes handing one over safe.

**A portfolio needs a reason.** The reason goes in the file, and it is what a
reviewer reads when they ask why this person could do that. Grant only what
somebody needs.

**Accounts are never deleted, only stood down.** Every judgment, certification
and upload points at an account; removing one would orphan the record it
authorised. Standing an account down keeps the trail and closes the door.

## Reading the cost record

`CONTROLLER`, `AUDITOR` and `ORG_ADMIN` — including you — read the cost record
by rank. `SYSTEM_ADMIN` does not, because that account may belong to somebody
outside the organisation.

Where such a person genuinely needs it — an engagement lead working under a
non-disclosure agreement — `record_access` carries it, and it is granted by
**YBI's own administrator** to the account above them in rank. That direction
is deliberate: the data is yours, so you are who lets somebody read it.

## The forty

The payroll register has forty-three people. Six have accounts. The other
forty are listed on the People screen with **no account**, because the
register carries surnames only and their addresses would have to be guessed —
and an account at a guessed address is one nobody can sign into.

They are a gap you close by finding out real addresses, one at a time, not by
inventing a naming convention. Where an address was derived, the screen marks
it unconfirmed until somebody checks it; correct it in place.

Each of those forty people owes a certification that only they can sign, so
until they have accounts the labour evidence stays a reconstruction.

## What the nav does and does not tell you

The nav shows what is **yours to do**. It is not a security boundary: you can
read the cost record by rank, so some screens are reachable by URL even though
no tab offers them. That is not a hole — every one of those is a read, and the
gates that decide who may write are unchanged by whether a tab is drawn.

What the nav must never do is show a tab that answers 403. If you ever see
one, that is a defect worth reporting.
