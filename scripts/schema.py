#!/usr/bin/env python3
"""What is actually in the database, for the moment before you write a query.

    python scripts/schema.py                    everything, one line each
    python scripts/schema.py ledger_line        that table, column by column
    python scripts/schema.py evidence_grade     that enum, value by value
    python scripts/schema.py --like wage        anything whose name contains it

The reason this exists is a defect made six times in one week: a column name,
a table name and an enum value each recalled rather than read —
``ledger_import.loaded_by`` for ``imported_by``, ``audit_log.actor_name`` for
``actor``, ``award_term.key`` for ``term_key``, ``'RECONSTRUCTED'`` for
``MANAGEMENT_RECONSTRUCTION``. Every one cost a round trip through a running
service to find out.

``tests/test_sql_is_real.py`` is the half that catches it without being
asked. This is the half for when you are writing the query rather than
running it, and it prints the two things guessing gets wrong: the exact
column name, and — for an enum column — the values it will actually take,
inline, because that is the one you cannot infer from anything.

Reads ``DATABASE_URL``. Nothing here writes.
"""

from __future__ import annotations

import difflib
import os
import sys

import psycopg
from psycopg.rows import dict_row

COLUMNS = """
SELECT a.attname                                    AS column,
       format_type(a.atttypid, a.atttypmod)         AS type,
       NOT a.attnotnull                             AS nullable,
       pg_get_expr(d.adbin, d.adrelid)              AS default,
       t.typtype = 'e'                              AS is_enum,
       CASE WHEN t.typtype = 'e' THEN
         (SELECT array_agg(e.enumlabel ORDER BY e.enumsortorder)
            FROM pg_enum e WHERE e.enumtypid = t.oid) END AS values
  FROM pg_attribute a
  JOIN pg_class c    ON c.oid = a.attrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_type t     ON t.oid = a.atttypid
  LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
 WHERE n.nspname = 'public' AND c.relname = %s
   AND a.attnum > 0 AND NOT a.attisdropped
 ORDER BY a.attnum
"""

RELATIONS = """
SELECT c.relname AS name,
       CASE c.relkind WHEN 'r' THEN 'table' WHEN 'v' THEN 'view'
                      WHEN 'm' THEN 'materialised' WHEN 'p' THEN 'table'
                      ELSE c.relkind::text END AS kind
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r','v','m','p')
 ORDER BY c.relkind, c.relname
"""

ENUMS = """
SELECT t.typname AS name,
       array_agg(e.enumlabel ORDER BY e.enumsortorder) AS values
  FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
  JOIN pg_namespace n ON n.oid = t.typnamespace
 WHERE n.nspname = 'public'
 GROUP BY t.typname ORDER BY t.typname
"""

CHECKS = """
SELECT conname AS name, pg_get_constraintdef(oid) AS rule
  FROM pg_constraint
 WHERE conrelid = %s::regclass AND contype IN ('c','u','f','p')
 ORDER BY contype, conname
"""

TRIGGERS = """
SELECT tgname AS name, pg_get_triggerdef(oid) AS def
  FROM pg_trigger WHERE tgrelid = %s::regclass AND NOT tgisinternal
 ORDER BY tgname
"""


def show_relation(cur, name: str) -> None:
    cur.execute(COLUMNS, (name,))
    cols = cur.fetchall()
    if not cols:
        return
    cur.execute(RELATIONS)
    kind = next((r["kind"] for r in cur.fetchall() if r["name"] == name), "?")
    print(f"\n{name}  ({kind})\n" + "─" * 72)
    width = max(len(c["column"]) for c in cols)
    for c in cols:
        line = f"  {c['column']:<{width}}  {c['type']}"
        if not c["nullable"]:
            line += "  NOT NULL"
        if c["default"]:
            line += f"  = {c['default']}"
        print(line)
        if c["is_enum"]:
            # The one thing that cannot be guessed from anything else.
            print(" " * (width + 4) + "  " + " | ".join(c["values"]))
    if kind != "table":
        return
    cur.execute(CHECKS, (name,))
    rules = cur.fetchall()
    if rules:
        print("\n  constraints")
        for r in rules:
            print(f"    {r['name']}: {r['rule']}")
    cur.execute(TRIGGERS, (name,))
    trigs = cur.fetchall()
    if trigs:
        print("\n  triggers")
        for t in trigs:
            print(f"    {t['name']}")


def show_enum(cur, name: str) -> bool:
    cur.execute(ENUMS)
    for row in cur.fetchall():
        if row["name"] == name:
            print(f"\n{name}  (enum)\n" + "─" * 72)
            for v in row["values"]:
                print(f"  {v}")
            return True
    return False


def main() -> int:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2
    args = sys.argv[1:]
    with psycopg.connect(dsn, row_factory=dict_row) as c, c.cursor() as cur:
        cur.execute(RELATIONS)
        rels = cur.fetchall()
        cur.execute(ENUMS)
        enums = cur.fetchall()
        names = [r["name"] for r in rels] + [e["name"] for e in enums]

        if not args:
            for kind in ("table", "view", "materialised"):
                group = [r["name"] for r in rels if r["kind"] == kind]
                if group:
                    print(f"\n{kind}s ({len(group)})\n" + "─" * 72)
                    for n in group:
                        print(f"  {n}")
            print(f"\nenums ({len(enums)})\n" + "─" * 72)
            for e in enums:
                print(f"  {e['name']:<24} {' | '.join(e['values'])}")
            return 0

        if args[0] == "--like":
            needle = args[1].lower()
            hits = [n for n in names if needle in n.lower()]
            print("\n".join(hits) if hits else f"nothing matching {needle!r}")
            return 0 if hits else 1

        missing = []
        for want in args:
            if want in [r["name"] for r in rels]:
                show_relation(cur, want)
            elif show_enum(cur, want):
                pass
            else:
                missing.append(want)
        for want in missing:
            near = difflib.get_close_matches(want, names, n=5, cutoff=0.5)
            print(f"\nthere is no {want!r} in this database.", file=sys.stderr)
            if near:
                print("did you mean: " + ", ".join(near), file=sys.stderr)
        return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
