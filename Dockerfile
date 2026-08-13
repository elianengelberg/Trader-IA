# Trader-IA — simulation-only paper-trading platform.
#
# Two stages: the dashboard is built with Node and copied into a Python image that has no
# Node in it. The runtime image therefore carries no build toolchain, which is both
# smaller and a smaller attack surface.
#
# The default configuration needs no daemon, no credential and no network: SQLite, an
# in-process event bus, seeded synthetic market data and the offline LLM mock.

# ---------------------------------------------------------------- frontend
FROM node:22-slim AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-fund --no-audit 2>/dev/null || npm install --no-fund --no-audit

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------- runtime
FROM python:3.11-slim AS runtime

# curl is here for the healthcheck below and nothing else.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# A non-root user. The application writes only to /app/data, which is owned by it.
RUN useradd --create-home --uid 10001 tia

WORKDIR /app

COPY pyproject.toml README.md ./
COPY packages/ ./packages/
RUN pip install --no-cache-dir -e ".[api,db]"

COPY data/fixtures/ ./data/fixtures/
COPY scripts/ ./scripts/
COPY docs/ ./docs/
COPY --from=frontend /build/dist ./frontend/dist

RUN mkdir -p /app/data/runtime && chown -R tia:tia /app/data
USER tia

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TIA_ENV=demo \
    TIA_HOST=0.0.0.0 \
    TIA_PORT=8000 \
    TIA_DATABASE_URL=sqlite+aiosqlite:////app/data/runtime/tia.db

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=4s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["python", "-m", "uvicorn", "tia.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "/dev/null"]
