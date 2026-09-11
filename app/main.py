"""
YBI Cost Allocation — application entry point.

One process. FastAPI serves the JSON API under /api and the built React app
everywhere else, so Railway runs a single service with a single deploy.

Migrations run on startup from app/sql/*.sql in filename order. They are
idempotent and tracked in schema_migration, so a redeploy is safe.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import storage
from app.db import close_pool, open_pool, run_migrations
from app.domain.segment import SegmentError
from app.routers import (auth, awards, certify, chart, classify, contracts,
                         dashboard,
                         documents, evidence, export, facilities, health,
                         imports, lanes, rates, reconcile, restate, review,
                         timesheet, undo)
from app.settings import settings

log = logging.getLogger("ybi")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


def check_deployment() -> None:
    """Refuse to serve a deployment that is configured as development.

    ``env`` decides two things that are invisible when they are wrong: the
    session cookie's Secure flag, and whether CORS admits the Vite dev server.
    A production deployment left at the default would look entirely healthy
    while handing out cookies that a plain-HTTP hop can read. Railway sets
    RAILWAY_ENVIRONMENT_NAME on every service, so the mismatch is detectable,
    and a boot that stops is cheaper than one that does not.
    """
    if os.getenv("RAILWAY_ENVIRONMENT_NAME") and settings.env == "dev":
        raise RuntimeError(
            "YBI_ENV is 'dev' on a Railway deployment. Session cookies would "
            "be issued without the Secure flag and CORS would admit "
            "localhost:5173. Set YBI_ENV=prod on the service and redeploy.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_deployment()
    open_pool()
    applied = run_migrations()
    if applied:
        log.info("applied migrations: %s", ", ".join(applied))

    # The volume's shape, created before anybody looks at it. Somebody who
    # opens the volume on the first day should see what it is for and be
    # able to tell a correctly-mounted volume from a broken one; an empty
    # directory tells them neither.
    made = storage.ensure_skeleton()
    log.info("storage at %s%s", storage.ROOT,
             f" — created {len(made)} directories" if made else "")

    log.info("ready — period %s, env %s", settings.period, settings.env)
    yield
    close_pool()


app = FastAPI(
    title="YBI Cost Allocation",
    description="Cost pool build-up, allocation and audit package for 2 CFR 200 compliance.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"] if settings.env == "dev" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (health, auth, dashboard, imports, chart, classify, lanes,
          rates, evidence, documents, awards, facilities, certify,
          timesheet, undo, restate, review, contracts, reconcile,
          export):
    app.include_router(r.router, prefix="/api")


@app.exception_handler(ValueError)
async def value_error_handler(_, exc: ValueError):
    # Domain validation failures are user-facing, not server faults.
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(SegmentError)
async def segment_error_handler(_, exc: SegmentError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


#: Constraint names are precise and unreadable. Where a person can actually
#: hit one, say what it means; where they cannot, name the constraint so
#: whoever reads the log has something to search for.
CONSTRAINT_MESSAGES = {
    "one_live_entry_per_day_objective":
        "There is already time recorded against that objective on that day.",
    "one_live_submission_per_period":
        "This timesheet is already submitted for the period.",
    "timesheet_hours_sane":
        "Hours have to be more than zero and no more than twenty-four.",
    "as_worked_must_be_prompt":
        "A record made as the work was done has to be entered within a week "
        "of it. Say what you are working from instead.",
    "employment_hours_sane":
        "Contracted hours have to be between one and eighty a week.",
    "employment_span_ordered":
        "The end of an employment span cannot precede its start.",
    "one_live_decision_per_line":
        "That line already carries a live decision.",
    "one_live_decision_per_unit":
        "That analytical unit already carries a live decision.",
    "reconstruction_needs_rationale":
        "A reconstructed figure has to carry its reasoning.",
    "reconstruction_not_unsupported":
        "A reconstruction cannot be offered while the evidence behind it is "
        "graded unsupported.",
    "certification_statement_present":
        "A certification has to carry the words that were signed.",
    "own_subsidy_is_not_cost_share":
        "Letting your own space or equipment below market is not cost share. "
        "2 CFR 200.465 allows a less-than-arm's-length rental only up to what "
        "ownership would have cost, so forgone rent on your own building is "
        "not a cost you incurred. Record it as mission value — it is worth "
        "having, it just does not go on a federal report.",
    "unrecovered_indirect_needs_approval":
        "Unrecovered indirect cost can be cost share only with the awarding "
        "agency's prior written approval (2 CFR 200.306(c)). Record the "
        "approval reference, or leave it unclaimed until you have one.",
    "unit_market_needs_basis":
        "A market rate needs to say where it came from — a comparable, a "
        "survey, an appraisal. A rate with no basis is a number somebody "
        "made up.",
    "asset_market_rate_needs_basis":
        "An hourly rate for equipment needs to say what it rests on.",
    "in_kind_basis_present":
        "An in-kind value has to say how it was arrived at.",
    "leased_names_a_landlord":
        "A building YBI does not own has a landlord. Name them.",
    "unit_occupied_names_occupant":
        "A space marked occupied has somebody in it. Name them.",
    "facility_rentable_sane":
        "Rentable area includes the common area load, so it cannot be less "
        "than usable area.",
}


def _constraint_message(exc: Exception) -> str:
    name = getattr(getattr(exc, "diag", None), "constraint_name", None) or ""
    if name in CONSTRAINT_MESSAGES:
        return CONSTRAINT_MESSAGES[name]
    if name:
        return f"The database refused this write: {name}."
    return "The database refused this write."


@app.exception_handler(psycopg.errors.UniqueViolation)
async def unique_handler(_, exc: psycopg.errors.UniqueViolation):
    """A duplicate is a conflict, not a server fault.

    Several of the invariants here are partial unique indexes — one live
    decision per line, one live timesheet entry per day and objective — so
    hitting one is a normal outcome of two people working at once, and the
    screen should say so rather than showing a 500.
    """
    log.info("unique violation: %s", _constraint_message(exc))
    return JSONResponse(status_code=409,
                        content={"error": "CONFLICT",
                                 "message": _constraint_message(exc)})


@app.exception_handler(psycopg.errors.CheckViolation)
async def check_handler(_, exc: psycopg.errors.CheckViolation):
    return JSONResponse(status_code=422,
                        content={"error": "REFUSED",
                                 "message": _constraint_message(exc)})


@app.exception_handler(psycopg.errors.ForeignKeyViolation)
async def fk_handler(_, exc: psycopg.errors.ForeignKeyViolation):
    """Something referred to a row that does not exist — an objective that is
    not in the chart, a period that was never opened."""
    return JSONResponse(
        status_code=422,
        content={"error": "UNKNOWN_REFERENCE",
                 "message": "That refers to something the system does not "
                            "have on file. Check the objective, period or "
                            "account it names."})


@app.exception_handler(psycopg.errors.NotNullViolation)
async def not_null_handler(_, exc: psycopg.errors.NotNullViolation):
    column = getattr(getattr(exc, "diag", None), "column_name", "") or "a field"
    return JSONResponse(status_code=422,
                        content={"error": "MISSING",
                                 "message": f"{column} is required."})


@app.exception_handler(psycopg.errors.RaiseException)
async def gate_handler(_, exc: psycopg.errors.RaiseException):
    """A schema gate declining a write is an expected outcome.

    The invariants in app/sql live in triggers that RAISE, which reaches the
    handler as a database error and would otherwise render as a bare 500. The
    controller needs to read "a VERIFIED classification requires at least one
    attached document", not "Internal Server Error" — the message is the whole
    point of putting the rule in the schema.
    """
    message = str(exc).split("\n")[0].strip()
    log.info("gate refused a write: %s", message)
    return JSONResponse(status_code=409,
                        content={"detail": {"error": "SCHEMA_GATE",
                                            "message": message}})


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        candidate = WEB_DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
else:
    @app.get("/", include_in_schema=False)
    async def no_ui():
        return {"status": "api only",
                "hint": "run `npm --prefix web run build`, or use the Vite dev server",
                "docs": "/api/docs"}
