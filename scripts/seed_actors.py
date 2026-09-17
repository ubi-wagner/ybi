#!/usr/bin/env python3
"""Bootstrap the four actors.

The first ADMIN cannot be created through the API — provisioning requires an
ADMIN — so it is written directly, out of band, which is what a bootstrap is.

Passwords come from the environment. There are no defaults: a seed script that
invents a password is a seed script that ships one to production.

    YBI_SEED_PASSWORD=... python3 scripts/seed_actors.py
"""

from __future__ import annotations

import os
import sys

from app.auth import hash_password
from app.db import execute, one, open_pool
from app.foundation import EMAIL  # noqa: E402

ACTORS = [
    ("eric.c.wagner@gmail.com", "Eric Wagner", "ADMIN", None),
    (EMAIL["tom"], "Tom Metzinger", "CONTROLLER", None),
    ("auditor@ybi.org", "Engagement Auditor", "AUDITOR", None),
    ("bewing@ybi.org", "Barb Ewing", "EMPLOYEE", "EWING"),
    ("sgaffney@ybi.org", "Stephanie Gaffney", "EMPLOYEE", "GAFFNEY"),
]


def main() -> int:
    password = os.environ.get("YBI_SEED_PASSWORD", "")
    if not password:
        print("YBI_SEED_PASSWORD is required. No default is provided on purpose.",
              file=sys.stderr)
        return 2
    if len(password) < 12:
        print("YBI_SEED_PASSWORD must be at least 12 characters.", file=sys.stderr)
        return 2

    open_pool()
    for email, name, role, employee_key in ACTORS:
        if one("SELECT 1 FROM actor WHERE email=%s", (email,)):
            print(f"  exists   {email:32s} {role}")
            continue
        execute("""INSERT INTO actor (email, display_name, role, password_hash,
                                      employee_key)
                   VALUES (%s,%s,%s,%s,%s)""",
                (email, name, role, hash_password(password), employee_key))
        print(f"  created  {email:32s} {role}"
              + (f"  -> {employee_key}" if employee_key else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
