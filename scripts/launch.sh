#!/usr/bin/env bash
# One-line local launch: installs locked dependencies, builds the UI, and
# serves the app at http://localhost:8000. Set OPENAI_API_KEY and AIRA_MODEL
# in .env (see .env.example) for live assessment work.
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --project backend --locked
npm --prefix frontend ci
npm --prefix frontend run build
exec uv run --project backend --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
