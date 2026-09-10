#!/usr/bin/env bash
# Two terminals in one: API on :8000, Vite on :5173 proxying /api.
set -euo pipefail
docker compose up -d db
export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/ybi}"
until docker compose exec -T db pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
uvicorn app.main:app --reload --port 8000 &
API=$!
trap 'kill $API 2>/dev/null || true' EXIT
npm --prefix web install
npm --prefix web run dev
