.PHONY: install check backend-check frontend-check browser-test dev-api dev-ui

install:
	uv sync --project backend --locked
	npm --prefix frontend ci

backend-check:
	uv run --project backend --locked ruff check --config backend/pyproject.toml backend/app tests
	uv run --project backend --locked ruff format --config backend/pyproject.toml --check backend/app tests
	uv run --project backend --locked mypy --config-file backend/pyproject.toml backend/app
	uv run --project backend --locked pytest -c backend/pyproject.toml
	uv build backend --out-dir backend/dist

frontend-check:
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck
	npm --prefix frontend test
	npm --prefix frontend run build

check: backend-check frontend-check

browser-test:
	npm --prefix frontend run build
	npm --prefix frontend run test:e2e

dev-api:
	uv run --project backend uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-ui:
	npm --prefix frontend run dev
