# Provisioning on Railway

One service, one Postgres, one volume. Merge to `main` deploys it.

```
Railway project
├── ybi-cost      ← this repo, Dockerfile builder, public domain
│                   volume mounted at /srv/storage  (evidence lives here)
└── Postgres      ← attached; DATABASE_URL is injected by reference
```

There is no worker, no queue, no second database and no object store. The
React app is built in the node stage of the Dockerfile and served by the same
FastAPI process that serves `/api`, so the browser and the API are the same
origin and the session cookie needs no cross-site handling.

---

## Step 1 — Create the project and the database

1. railway.app → **New Project** → **Deploy from GitHub repo** → `ubi-wagner/ybi`.
2. Cancel the first deploy; there is nothing for it to connect to yet.
3. **+ New → Database → PostgreSQL.** A stock instance is enough — no
   `pgvector`, no `uuid-ossp`. `001_core.sql` runs `CREATE EXTENSION IF NOT
   EXISTS pgcrypto` itself, which the role behind Railway's injected
   `DATABASE_URL` is entitled to do, so there is nothing to enable by hand.

## Step 2 — Configure the service

Rename the service to `ybi-cost`.

**Settings → Build**

| | |
|---|---|
| Builder | `Dockerfile` |
| Dockerfile path | `Dockerfile` |
| Build context | repository root (**not** a subdirectory) |

**Settings → Deploy** — `railway.json` already sets these; check they took:

| | |
|---|---|
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/api/health` |
| Health check timeout | 60s |
| Restart policy | on failure, 3 retries |

**Settings → Volumes → + New Volume**

| | |
|---|---|
| Mount path | `/srv/storage` |
| Size | 5 GB to start |

This one is not optional and it is not recoverable after the fact. Evidence
uploads are written to `YBI_STORAGE_DIR` on the container filesystem, which
Railway discards on every deploy. Without the volume, every invoice, lease and
timesheet Tom attaches disappears the next time anyone pushes to `main` — and
the register still lists them, so the loss is silent until an auditor asks for
a document. Mount the volume **before** the first upload.

## Step 3 — Variables

Legend: ⛔ the service will not start without it · ⚙️ Railway injects it ·
○ optional · 💤 read by no code.

| Variable | Purpose | Status |
|---|---|---|
| `DATABASE_URL` | **+ Reference** → the Postgres service. Read unprefixed by convention, ahead of `YBI_DATABASE_URL` | ⛔ |
| `YBI_JWT_SECRET` | Signs session cookies. **At least 32 bytes** — `app/auth.py` refuses to authenticate anyone with a shorter one rather than signing weakly. Generate: `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'` | ⛔ |
| `YBI_ENV` | `prod`. Sets the session cookie's `Secure` flag and closes CORS. The service **refuses to boot** on Railway while this says `dev`, because that misconfiguration is otherwise invisible: everything works, over an insecure cookie | ⛔ |
| `YBI_PERIOD` | `2025`. The period every screen defaults to | ○ (defaults to 2025) |
| `YBI_STORAGE_DIR` | `/srv/storage` — must equal the volume mount path | ⛔ once a volume exists |
| `YBI_SEED_PASSWORD` | Bootstrap password for `scripts/seed_actors.py`. Set it, seed, then **delete the variable** — see step 5 | ○ (seeding only) |
| `S3_BUCKET` · `S3_ENDPOINT` · `S3_ACCESS_KEY` · `S3_SECRET_KEY` | Object-store offload is configured for but **not implemented**: `app/routers/evidence.py` writes to the local path regardless of these. Setting them does nothing | 💤 |
| `PORT` · `RAILWAY_ENVIRONMENT_NAME` · `RAILWAY_GIT_COMMIT_SHA` | injected | ⚙️ |

## Step 4 — Migrations

**There is nothing to run.** `app/main.py` applies `app/sql/*.sql` in filename
order at startup, inside one transaction, tracked in `schema_migration`, under
a session advisory lock so the old and new containers of a rolling deploy
cannot both apply the same file. A migration that fails aborts the boot, the
health check never goes green, and Railway keeps the previous deployment
serving.

So: **do not run migrations by hand.** Two runners against one database is the
exact race the advisory lock exists to prevent, and the lock only protects the
in-deployment path.

Watch the first deploy's logs. A clean first boot says:

```
INFO ybi.db migrating 001_core.sql
…
INFO ybi.db migrating 015_export_activity.sql
INFO ybi applied migrations: 001_core.sql, …
INFO ybi ready — period 2025, env prod
```

Two rules that hold forever after that:

- **Never edit a migration that has already been applied.** It will not
  re-run, so production and the file diverge silently. Add a numbered file.
- Numbering is the order. `016_*.sql` runs after `015_*.sql` because of the
  filename, not because of when it was committed.

## Step 5 — Seed the accounts

The first ADMIN cannot be created through the API, because creating an actor
requires an ADMIN. That is what a bootstrap is, and `scripts/seed_actors.py`
is it. The script ships inside the image, so it runs against the private
database URL without exposing the database to the internet:

```bash
railway run --service ybi-cost -- python scripts/seed_actors.py
```

It provisions five accounts — Eric (ADMIN), Tom (CONTROLLER), the engagement
auditor (AUDITOR), and Barb and Stephanie (EMPLOYEE, each bound to the
employee they certify for). It refuses to run without `YBI_SEED_PASSWORD` and
refuses a password under twelve characters; it never invents one.

**All five accounts start with that same password.** So the order is: seed,
run the boundary drive in step 7 while they still share it, then hand them
over:

1. Have each person sign in and use **Password** in the top bar to set their
   own. The endpoint requires the current password, so nobody can be locked
   out of their own account from a borrowed screen.
2. Delete `YBI_SEED_PASSWORD` from the Railway variables once everyone has.

Until each person holds a password only they know, every signature in the
system is one that four other people could have written — which is precisely
what the record exists to rule out. Re-running the seed is safe: it skips
accounts that already exist and will not reset a password anyone has changed.

## Step 6 — Load 2025

Sign in as Tom and use **Import** (schedule A). In order:

1. **Profit and Loss** — first, always. It defines which accounts are cost and
   which are balance sheet. Without it the classification queue offers bank
   accounts for classification.
2. **General Ledger.**
3. **Balance Sheet**, when the asset register arrives.

Nothing reaches the ledger until every subtotal QuickBooks printed in its own
report matches what was parsed, so a refused import means the export was
filtered or mis-dated, not that the deploy is broken. Nothing is written on a
refusal.

Effort distributions have no import screen yet. Upload the Grant
Reconciliation Workbook through **Evidence**, note the `EV-…` id it is filed
under, then:

```bash
railway run --service ybi-cost -- python scripts/load_labor.py --evidence EV-8be4dad4402d
```

It loads from the stored copy, so the workbook the load used is the workbook
on file, hash and all. `scripts/load_2025.py` and `scripts/tom_session.py` are
development harnesses — they read source workbooks from `docs/`, which are
deliberately **not** in the image, and they are not part of provisioning.

## Step 7 — Verify

```bash
curl https://<your-domain>/api/health
# {"status":"ok","database":"up","period":"2025","env":"prod"}
```

`env` must read `prod`. Then sign in as Tom, confirm the dashboard's income
and expenses tie to the P&L you imported, and check that **Recent activity**
shows your own sign-in. That last one proves the audit spine is writing.

The access boundaries can be proved against the deployment itself:

```bash
YBI_SEED_PASSWORD=... python3 scripts/drive_actors.py --base https://<your-domain>
```

Twenty-one checks: the auditor reads the ledger and is refused a
classification, a seal, a note and a split; an employee is refused the ledger
and another person's certification; anonymous requests are refused everything.
Exit 0 is a pass, exit 2 means it **could not run**, which is not a pass — a
logged-out client and a deny-all look identical, so the drive proves it can
read real rows before it claims a boundary held.

Two things about when to run it. Point it at the `https://` domain, not at a
plain-HTTP host: in `prod` the session cookie carries `Secure`, so an HTTP
client never sends it back and every check after sign-in fails as a false
negative. And run it **while the accounts still share the bootstrap
password** — it signs in as all four actors with the one value in
`YBI_SEED_PASSWORD`, so once people have set their own it can no longer drive
them. Verify, then hand the accounts over.

---

## Ongoing

Merge to `main` is the whole deploy: CI runs `pytest` against a Postgres 16
service, Railway rebuilds, migrations apply inside the deployment, the health
check gates the cutover. Nobody edits the database by hand.

## Troubleshooting

**Boot aborts with "YBI_ENV is 'dev' on a Railway deployment"** — set
`YBI_ENV=prod`. The guard is deliberate; the failure it prevents is invisible.

**Health check fails, logs show a migration error** — the previous deployment
is still serving. Fix the SQL, push a new numbered file, redeploy. Do not edit
the file that failed if any part of it applied.

**"Not signed in" immediately after signing in** — `YBI_JWT_SECRET` changed
between deploys, or is shorter than 32 bytes. Every existing session dies when
it changes; that is correct, but it should not be changing.

**Uploads vanish after a deploy** — the volume is not mounted, or
`YBI_STORAGE_DIR` does not match its mount path. Documents uploaded before the
volume existed are gone; their register rows remain, and the download route
answers 410 rather than pretending.

**A rate cannot be computed** — that is the design, not a fault. Nothing
computes a rate until the decision set is sealed, and the database trigger
`rate_requires_seal` refuses a rate whose seal does not match a sealed set.
