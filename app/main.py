"""
YBI Cost Allocation — application entry point.

One process. FastAPI serves the JSON API under /api and the built React app
everywhere else, so Railway runs a single service with a single deploy.

Migrations run on startup from app/sql/*.sql in filename order. They are
idempotent and tracked in schema_migration, so a redeploy is safe.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import close_pool, open_pool, run_migrations
from app.routers import awards, chart, classify, evidence, health, imports, lanes, rates
from app.settings import settings

log = logging.getLogger("ybi")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    applied = run_migrations()
    if applied:
        log.info("applied migrations: %s", ", ".join(applied))
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

for r in (health, imports, chart, classify, lanes, rates, evidence, awards):
    app.include_router(r.router, prefix="/api")


@app.exception_handler(ValueError)
async def value_error_handler(_, exc: ValueError):
    # Domain validation failures are user-facing, not server faults.
    return JSONResponse(status_code=422, content={"detail": str(exc)})


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
