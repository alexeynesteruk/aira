FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    AIRA_FRONTEND_DIR=/app/frontend/dist \
    AIRA_DATA_DIR=/app/data \
    PATH="/app/backend/.venv/bin:$PATH"
COPY backend/pyproject.toml backend/uv.lock /app/backend/
RUN uv sync --project backend --locked --no-dev --no-install-project
COPY backend/app/ /app/backend/app/
RUN uv sync --project backend --locked --no-dev --no-editable \
    && useradd --uid 10001 --create-home aira \
    && mkdir /app/data && chown aira:aira /app/data
COPY --from=frontend /build/frontend/dist/ /app/frontend/dist/
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health/live', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
