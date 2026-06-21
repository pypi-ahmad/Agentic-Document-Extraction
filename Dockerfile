# Multi-stage Dockerfile for agentic-document-extraction v0.3.0.
#
# Stage 1 (builder): uses uv to resolve and sync the project deps from
# the locked pyproject.toml + uv.lock. uv runs in a non-slim image so
# the build cache is portable.
#
# Stage 2 (runtime): python:3.12.10-slim + the resolved venv from stage 1.
# Runs as a non-root user. The container exposes 8000.

# ─────────────────────────────────────────────────────────────────────
# Stage 1 — builder
# ─────────────────────────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Sync the full dependency set (no dev extras) into a venv we can copy.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Install the project itself in editable mode, then drop the egg-info
# (we ship a flat source tree in the runtime image).
COPY backend ./backend
COPY alembic.ini ./
COPY backend/alembic ./backend/alembic
RUN uv sync --frozen --no-dev

# ─────────────────────────────────────────────────────────────────────
# Stage 2 — runtime
# ─────────────────────────────────────────────────────────────────────
FROM python:3.12.10-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0

# Minimal runtime system packages: tini for proper signal handling,
# curl for healthchecks, and the build deps for PyMuPDF's native bits.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        tini \
        curl \
        libstdc++6 \
 && rm -rf /var/lib/apt/lists/*

# Non-root user.
RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

# Copy the resolved venv and the project source from the builder.
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/backend /app/backend
COPY --from=builder --chown=app:app /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=app:app /app/backend/alembic /app/backend/alembic
COPY --from=builder --chown=app:app /app/pyproject.toml /app/pyproject.toml
COPY --from=builder --chown=app:app /app/uv.lock /app/uv.lock

# Runtime data dirs (mounted as volumes in compose / k8s).
RUN mkdir -p /app/data/uploads /app/data/artifacts /app/data/db \
 && chown -R app:app /app/data

ENV PATH=/app/.venv/bin:$PATH \
    UPLOAD_DIR=/app/data/uploads \
    ARTIFACTS_DIR=/app/data/artifacts \
    DATABASE_URL=sqlite+aiosqlite:////app/data/db/extraction.db

USER app

EXPOSE 8000

# Tini is PID 1 — it forwards SIGTERM to uvicorn so the lifespan
# shutdown handler drains the in-process queue.
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default command: run uvicorn against the FastAPI app. The host and
# port come from env (set above). ``--proxy-headers`` lets uvicorn
# honour X-Forwarded-* from a reverse proxy.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--app-dir", "backend"]
