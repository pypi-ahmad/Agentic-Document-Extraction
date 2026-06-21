# justfile - https://github.com/casey/just
# Run `just` (no args) to list available recipes.

set dotenv-load := true

# Default recipe lists the available recipes.
default:
    @just --list

# ── Setup ────────────────────────────────────────────────────────────

# Create the venv and install dev + runtime dependencies.
install:
    uv venv --python 3.12.10 .venv
    @just sync

# Sync dependencies (idempotent; uses uv.lock).
sync:
    uv sync --frozen --extra test --extra lint --extra ollama

# Run a one-off command inside the venv.
run *args:
    .venv/bin/python {{ args }}

# ── Linting and formatting ──────────────────────────────────────────

# Lint the Python source.
lint:
    .venv/bin/ruff check backend/app backend/tests scripts

# Auto-fix what's safe.
fix:
    .venv/bin/ruff check --fix backend/app backend/tests scripts

# Format the Python source.
fmt:
    .venv/bin/ruff format backend/app backend/tests scripts

# Check formatting (CI-friendly).
fmt-check:
    .venv/bin/ruff format --check backend/app backend/tests scripts

# Run pyright (basic mode; report-only).
typecheck:
    .venv/bin/pyright backend/app scripts/release.py || true

# ── Tests ────────────────────────────────────────────────────────────

# Run the full test suite.
test:
    .venv/bin/python -m pytest backend/tests/ -q

# Run the full test suite with coverage.
test-cov:
    .venv/bin/python -m pytest backend/tests/ --cov=app --cov-report=term-missing -q

# Run a single test by file (or by node-id substring).
test-one *args:
    .venv/bin/python -m pytest backend/tests/{{ args }}

# Run only the property-based tests.
test-props:
    .venv/bin/python -m pytest backend/tests/test_output_parser_property.py -v

# ── Running the app ──────────────────────────────────────────────────

# Run the backend on port 8000 with hot reload.
dev:
    .venv/bin/uvicorn app.main:app --reload --port 8000 --app-dir backend

# Run the backend on a chosen port.
serve port="8000":
    .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port {{ port }} --app-dir backend

# Start the full docker-compose stack (app + ollama).
up:
    docker compose up -d

# Tail logs from the running stack.
logs:
    docker compose logs -f

# Stop the stack.
down:
    docker compose down

# ── Database ─────────────────────────────────────────────────────────

# Create or upgrade the SQLite database to the latest Alembic revision.
migrate:
    alembic upgrade head

# Mark an existing v0.2.x database as caught up to the latest migration.
migrate-stamp-existing:
    alembic stamp head

# Generate a new migration from current model state.
migrate-new message:
    alembic revision --autogenerate -m "{{ message }}"

# Show the current revision.
migrate-current:
    alembic current

# ── Release ─────────────────────────────────────────────────────────

# Bump the version (patch|minor|major) and create a GitHub release.
release-patch:
    .venv/bin/python scripts/release.py --bump patch --push

release-minor:
    .venv/bin/python scripts/release.py --bump minor --push

release-major:
    .venv/bin/python scripts/release.py --bump major --push
